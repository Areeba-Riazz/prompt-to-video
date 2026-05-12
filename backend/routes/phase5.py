from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import logging
from typing import List, Dict, Any

from agents.edit_agent.intent_classifier import classify_edit_intent
from agents.edit_agent import edit_execution as edit_ex
from state_manager.snapshot import StateManager
from shared.schemas.state import MontageState

router = APIRouter()
logger = logging.getLogger("Phase5Route")

class EditRequest(BaseModel):
    query: str
    current_state: Dict[str, Any]

class RevertRequest(BaseModel):
    version: str

@router.post("/intent")
async def get_intent(req: EditRequest):
    """Parses a natural language edit query into a structured intent."""
    try:
        state_summary = edit_ex.summarize_state_for_intent(req.current_state)
        intent = classify_edit_intent(req.query, state_summary)
        return {"data": intent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/snapshot")
async def save_snapshot(req: Dict[str, Any]):
    """Saves a project snapshot (state + assets)."""
    try:
        state = req.get("state", {})
        summary = req.get("summary", "Manual snapshot")

        branch = req.get("truncate_after_version")
        if branch:
            removed = StateManager.truncate_future_after_version(str(branch))
            if removed:
                logger.info("🧹 [Phase5] Removed %d future snapshot(s) after %r", removed, branch)

        version = req.get("version", f"v{len(StateManager.history()) + 1}")
        assets = set()
        
        # 1. From final_scenes
        for scene in state.get("final_scenes", []):
            for key in ["final_video_path", "raw_mp4_path", "video_path", "audio_path"]:
                if scene.get(key) and os.path.exists(scene[key]):
                    assets.add(scene[key])
        
        # 2. From audio_tracks / video_tracks (intermediate)
        for track in state.get("audio_tracks", []):
            if track.get("audio_path") and os.path.exists(track["audio_path"]):
                assets.add(track["audio_path"])
        for track in state.get("video_tracks", []):
            if track.get("video_path") and os.path.exists(track["video_path"]):
                assets.add(track["video_path"])
        
        # 3. Final composite
        if state.get("final_output_path") and os.path.exists(state["final_output_path"]):
            assets.add(state["final_output_path"])
            
        entry = StateManager.snapshot(version, state, list(assets), summary)
        return {"data": entry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_history():
    """Returns the version history."""
    try:
        return {"data": StateManager.history()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/revert")
async def revert_state(req: RevertRequest):
    """Reverts the project to a previous version."""
    try:
        state = StateManager.revert(req.version)
        edit_ex.restore_phase1_disk_from_state(state)
        return {"data": state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_edit(req: Dict[str, Any]):
    """
    Executes a targeted re-run based on a parsed intent.
    Mutates a coalesced copy of state and persists Phase 1 artifacts when needed
    so LangGraph Phase 2 reload paths stay consistent.
    """
    intent = req.get("intent_obj", {})
    state = edit_ex.coalesce_edit_state(dict(req.get("state") or {}))
    target = intent.get("target")
    manifest_path = os.path.join(edit_ex.phase1_dir(), "scene_manifest.json")

    try:
        if target == "script":
            logger.info("📝 [Phase 5] Re-running Scriptwriter...")
            from agents.story_agent.agent import ScriptwriterAgent
            m_state = MontageState(**state)
            new_state = ScriptwriterAgent().generate(m_state)
            return {"data": new_state, "next_step": "phase1_full"}

        if target == "audio_fx":
            logger.info("🔊 [Phase 5] Routing to Audio Post-Production Suite...")
            raw_map = {
                intent.get("scope", "global"): {
                    **(intent.get("parameters") or {}),
                    "target": "audio_fx",
                }
            }
            state["post_proc_map"] = edit_ex.expand_post_proc_map_character_scopes(
                raw_map, manifest_path
            )
            state["skip_all_gen"] = True
            state["skip_video"] = False
            return {"data": state, "next_step": "phase2_partial"}

        if target == "video_fx":
            logger.info("🎞️ [Phase 5] Routing to Video Post-Production Suite...")
            raw_map = {
                intent.get("scope", "global"): {
                    **(intent.get("parameters") or {}),
                    "target": "video_fx",
                }
            }
            state["post_proc_map"] = edit_ex.expand_post_proc_map_character_scopes(
                raw_map, manifest_path
            )
            state["skip_all_gen"] = True
            state["skip_video"] = False
            return {"data": state, "next_step": "phase2_partial"}

        if target == "audio":
            logger.info("🎤 [Phase 5] Re-running Voice Synth...")
            state, dirty_chars, dirty_scenes = edit_ex.apply_audio_target_to_state(intent, state)
            if dirty_chars and isinstance(state.get("character_db"), list):
                edit_ex.persist_character_db(state["character_db"])
            if dirty_scenes and isinstance(state.get("scenes"), list):
                edit_ex.persist_scene_manifest_scenes(state["scenes"])

            state["skip_video"] = True
            state["skip_all_gen"] = False
            state["post_proc_map"] = {}
            return {"data": state, "next_step": "phase2_partial"}

        if target == "video_frame":
            scope = intent.get("scope", "")
            params = intent.get("parameters", {})
            scene_token = scope.split(":")[-1] if ":" in scope else ""
            logger.info("🖼️ [Phase 5] Re-running Video Gen for scope %r...", scope)
            try:
                scene_id_int = int(scene_token)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="video_frame intent requires scope like scene:1",
                )
            state, vf_changed = edit_ex.apply_video_frame_to_state(intent, state)
            if vf_changed and isinstance(state.get("scenes"), list):
                edit_ex.persist_scene_manifest_scenes(state["scenes"])
            state["skip_all_gen"] = False
            state["skip_video"] = False
            state["post_proc_map"] = {}
            return {
                "data": state,
                "next_step": "phase2_partial",
                "scene_id": scene_id_int,
            }

        if target == "video":
            logger.info("🎬 [Phase 5] Re-running Compositor...")
            from agents.video_agent.agent import compositor_node

            raw = edit_ex.coalesce_edit_state(dict(req.get("state") or {}))
            state = edit_ex.studio_state_for_compositor_edit(raw)

            if edit_ex.should_reuse_merge_for_bgm_intent(intent):
                state["_compositor_bgm_only"] = True

            user_query = str(req.get("user_query") or "")
            params = intent.get("parameters") or {}
            if intent.get("intent") != "remove_bgm" and params.get("apply_bgm") is not False:
                mood_guess, boost_guess = edit_ex.infer_bgm_mood_from_intent(intent, user_query)
                if mood_guess in edit_ex.BGM_MOODS:
                    state["_edit_bgm_mood"] = mood_guess
                if boost_guess:
                    state["_edit_bgm_boost"] = boost_guess

            if intent.get("intent") == "remove_subtitles":
                state["_compositor_enable_subtitles"] = False

            prev_bgm = os.environ.get("COMPOSITOR_BGM")
            if params.get("apply_bgm") is False or intent.get("intent") == "remove_bgm":
                os.environ["COMPOSITOR_BGM"] = "0"

            try:
                result = compositor_node(state)
            finally:
                if prev_bgm is None:
                    os.environ.pop("COMPOSITOR_BGM", None)
                else:
                    os.environ["COMPOSITOR_BGM"] = prev_bgm

            prev = dict(req.get("state") or {})
            merged = {**prev}
            if result.get("final_output_path"):
                merged["final_output_path"] = result["final_output_path"]
            if result.get("task_logs") is not None:
                merged["task_logs"] = result.get("task_logs")
            if result.get("status"):
                merged["status"] = result["status"]
            return {"data": merged, "next_step": "completed"}

        raise HTTPException(
            status_code=400,
            detail=f"Unsupported or unknown edit target: {target!r}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Edit execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
