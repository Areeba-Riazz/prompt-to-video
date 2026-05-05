from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
import os
import json
import logging

from agents.orchestrator.graph_phase2 import studio_floor_workflow
from shared.schemas.phase2_state import StudioState

router = APIRouter()
graph = studio_floor_workflow()
logger = logging.getLogger("Phase2Route")

# ── Endpoints for Phase 2 Production ────────────────────────────────────────

OUTPUT_ROOT = os.path.join("data", "outputs", "phase2")


def _build_initial_state(scene_id: int | None = None) -> StudioState:
    """Construct a clean StudioState for a new pipeline run."""
    char_db_path = os.path.join("data", "outputs", "phase1", "character_db.json")
    characters = []
    if os.path.exists(char_db_path):
        with open(char_db_path, "r") as f:
            cdata = json.load(f)
            characters = cdata.get("characters", []) if isinstance(cdata, dict) else cdata

    return StudioState(
        scene_manifest_path=os.path.join("data", "outputs", "phase1", "scene_manifest.json"),
        output_root=OUTPUT_ROOT,
        character_db=characters,
        scene_id_filter=scene_id,
        scenes=[],
        task_graph=[],
        scene_jobs=[],
        audio_tracks=[],
        video_tracks=[],
        face_swaps=[],
        final_scenes=[],
        final_output_path="",
        task_logs=[],
        status="idle",
        errors=[],
        current_agent="Supervisor",
    )


class RunRequest(BaseModel):
    scene_id: int | None = None


@router.post("/run")
async def run_phase2(req: RunRequest):
    """Triggers the Phase 2 production pipeline, optionally filtered by scene_id."""
    try:
        initial_state = _build_initial_state(scene_id=req.scene_id)

        logger.info("🎬 Starting Phase 2 Studio Floor production...")
        final_state = graph.invoke(initial_state)

        if final_state.get("status") == "failed":
            raise HTTPException(status_code=500, detail=f"Pipeline failed: {final_state.get('errors')}")

        # Dedupe by scene_id (legacy runs produced two finals per scene). Prefer last entry per id.
        finals_raw = final_state.get("final_scenes", []) or []
        by_sid: dict = {}
        for sc in finals_raw:
            try:
                sid = int(sc.get("scene_id", -1))
            except (TypeError, ValueError):
                continue
            if sid < 0:
                continue
            by_sid[sid] = sc

        scenes_out = []
        for sid in sorted(by_sid.keys()):
            sc = by_sid[sid]
            path = sc.get("final_video_path") or sc.get("raw_mp4_path")
            scenes_out.append({
                "scene_id": sid,
                "raw_mp4_path": path,
                "final_video_path": path,
                "method": sc.get("method"),
            })

        return {
            "data": {
                "status": "completed",
                "scenes": scenes_out,
            }
        }
    except Exception as e:
        logger.error(f"❌ Phase 2 execution failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compose")
async def compose_final(
    transition: str = "xfade",
    transition_duration: float = 0.5,
    enable_bgm: bool = True,
    enable_subtitles: bool = True,
    bgm_volume: float = 0.12,
):
    """
    Phase 3: Merge all generated scene_*.mp4 files into final_output.mp4.
    Applies cross-dissolve transitions, background music, and burned subtitles.
    Can be triggered independently of a full Phase 2 run.
    """
    scenes_dir = os.path.join(OUTPUT_ROOT, "final_scenes")
    if not os.path.isdir(scenes_dir) or not any(
        f.startswith("scene_") and f.endswith(".mp4")
        for f in os.listdir(scenes_dir)
    ):
        raise HTTPException(
            status_code=400,
            detail="No scene_*.mp4 files found. Run Phase 2 first to generate scene clips.",
        )

    # Set env flags before invoking compositor_node directly
    import os as _os
    _os.environ["COMPOSITOR_TRANSITION"] = transition
    _os.environ["COMPOSITOR_TRANSITION_S"] = str(transition_duration)
    _os.environ["COMPOSITOR_BGM"] = "1" if enable_bgm else "0"
    _os.environ["COMPOSITOR_BGM_VOLUME"] = str(bgm_volume)
    _os.environ["COMPOSITOR_SUBTITLES"] = "1" if enable_subtitles else "0"

    try:
        # Build a minimal state with scene_jobs populated from disk manifest
        initial_state = _build_initial_state()

        # Populate scene_jobs from manifest so subtitles have dialogue data
        scene_manifest_path = os.path.join("data", "outputs", "phase1", "scene_manifest.json")
        scene_jobs = []
        if os.path.exists(scene_manifest_path):
            with open(scene_manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            scenes = manifest if isinstance(manifest, list) else manifest.get("scenes", [])
            for scene in scenes:
                scene_id = scene.get("scene_id") or scene.get("id")
                if scene_id is not None:
                    scene_jobs.append({"scene_id": int(scene_id), "scene": scene, "task": scene})

        initial_state["scene_jobs"] = scene_jobs

        from agents.video_agent.agent import compositor_node
        result = compositor_node(initial_state)

        final_path = result.get("final_output_path", "")
        if not final_path or not os.path.exists(final_path):
            raise HTTPException(status_code=500, detail="Compositor did not produce a final output file.")

        size_mb = os.path.getsize(final_path) / 1_048_576
        return {
            "data": {
                "status": "completed",
                "final_output_path": final_path,
                "size_mb": round(size_mb, 2),
                "transition": transition,
                "bgm_enabled": enable_bgm,
                "subtitles_enabled": enable_subtitles,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Compose failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/final")
async def get_final_video():
    """Streams the composed final_output.mp4."""
    base_outputs = os.path.dirname(OUTPUT_ROOT)
    final_path = os.path.join(base_outputs, "final_output.mp4")
    if not os.path.exists(final_path):
        raise HTTPException(
            status_code=404,
            detail="final_output.mp4 not found. Click 'Finish Film' to compose the final movie.",
        )
    return FileResponse(
        final_path,
        media_type="video/mp4",
        headers={"Cache-Control": "no-store, max-age=0"},
        filename="final_output.mp4",
    )


@router.get("/final/status")
async def get_final_status():
    """Returns metadata about the latest composition result."""
    base_outputs = os.path.dirname(OUTPUT_ROOT)
    final_path = os.path.join(base_outputs, "final_output.mp4")
    meta_path = os.path.join(base_outputs, "phase3", "composition_metadata.json")

    exists = os.path.exists(final_path)
    size_mb = round(os.path.getsize(final_path) / 1_048_576, 2) if exists else None

    metadata = None
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

    return {
        "data": {
            "exists": exists,
            "size_mb": size_mb,
            "metadata": metadata,
        }
    }


@router.get("/outputs")
async def get_phase2_outputs():
    """Lists existing Phase 2 results from the centralized final_scenes folder."""
    final_dir = os.path.join(OUTPUT_ROOT, "final_scenes")
    scenes = []
    if os.path.exists(final_dir):
        for entry in os.listdir(final_dir):
            if entry.startswith("scene_") and entry.endswith(".mp4"):
                try:
                    scene_id = int(entry.replace("scene_", "").replace(".mp4", ""))
                    scenes.append({
                        "scene_id": scene_id,
                        "raw_mp4_path": os.path.join(final_dir, entry)
                    })
                except Exception:
                    continue

    return {"data": {"scenes": sorted(scenes, key=lambda x: x["scene_id"])}}


@router.get("/video/{scene_id}")
async def get_phase2_video(scene_id: int):
    """Streams the final MP4 from the centralized final_scenes folder."""
    video_path = os.path.join(OUTPUT_ROOT, "final_scenes", f"scene_{scene_id}.mp4")
    if os.path.exists(video_path):
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    raise HTTPException(status_code=404, detail="Video file not found.")
