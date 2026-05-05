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

class RunRequest(BaseModel):
    scene_id: int | None = None

@router.post("/run")
async def run_phase2(req: RunRequest):
    """Triggers the Phase 2 production pipeline, optionally filtered by scene_id."""
    try:
        # Load character_db from disk to pass into state
        char_db_path = os.path.join("data", "outputs", "phase1", "character_db.json")
        characters = []
        if os.path.exists(char_db_path):
            with open(char_db_path, "r") as f:
                cdata = json.load(f)
                characters = cdata.get("characters", []) if isinstance(cdata, dict) else cdata

        initial_state = StudioState(
            scene_manifest_path=os.path.join("data", "outputs", "phase1", "scene_manifest.json"),
            output_root=os.path.join("data", "outputs", "phase2"),
            character_db=characters,
            scene_id_filter=req.scene_id,
            scenes=[],
            task_graph=[],
            scene_jobs=[],
            audio_tracks=[],
            video_tracks=[],
            face_swaps=[],
            final_scenes=[],
            task_logs=[],
            status="idle",
            errors=[],
            current_agent="Supervisor"
        )

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

@router.get("/outputs")
async def get_phase2_outputs():
    """Lists existing Phase 2 results from the centralized final_scenes folder."""
    final_dir = os.path.join("data", "outputs", "phase2", "final_scenes")
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
                except: continue
    
    return {"data": {"scenes": sorted(scenes, key=lambda x: x["scene_id"])}}

@router.get("/video/{scene_id}")
async def get_phase2_video(scene_id: int):
    """Streams the final MP4 from the centralized final_scenes folder."""
    video_path = os.path.join("data", "outputs", "phase2", "final_scenes", f"scene_{scene_id}.mp4")
    if os.path.exists(video_path):
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    
    raise HTTPException(status_code=404, detail="Video file not found.")
