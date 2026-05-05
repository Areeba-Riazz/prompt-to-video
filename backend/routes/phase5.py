from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
import logging
from typing import List, Dict, Any

from agents.edit_agent.intent_classifier import classify_edit_intent
from state_manager.snapshot import StateManager
from agents.orchestrator.graph_phase1 import montage_workflow
from agents.orchestrator.graph_phase2 import studio_floor_workflow
from shared.schemas.state import MontageState
from shared.schemas.phase2_state import StudioState

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
        # We can pass a summary of the state to the LLM for better context
        state_summary = f"Project with {len(req.current_state.get('scenes', []))} scenes."
        intent = classify_edit_intent(req.query, state_summary)
        return {"data": intent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/snapshot")
async def save_snapshot(req: Dict[str, Any]):
    """Saves a project snapshot (state + assets)."""
    try:
        version = req.get("version", f"v{len(StateManager.history()) + 1}")
        state = req.get("state", {})
        summary = req.get("summary", "Manual snapshot")
        
        # Identify assets to back up (audio tracks, video files, final scenes)
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
        return {"data": state}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_edit(req: Dict[str, Any]):
    """
    Executes a targeted re-run based on a parsed intent.
    """
    intent = req.get("intent_obj", {})
    state = req.get("state", {})
    target = intent.get("target")
    
    try:
        if target == "script":
            # Re-run Phase 1 Scriptwriter
            logger.info("📝 [Phase 5] Re-running Scriptwriter...")
            from agents.story_agent.agent import ScriptwriterAgent
            m_state = MontageState(**state)
            new_state = ScriptwriterAgent().generate(m_state)
            return {"data": new_state, "next_step": "phase1_full"}
            
        elif target == "video_frame":
            # Re-run Image Generation for specific scene
            scope = intent.get("scope", "")
            params = intent.get("parameters", {})
            scene_id = scope.split(":")[-1]
            logger.info(f"🖼️ [Phase 5] Re-running Video Gen for Scene {scene_id}...")
            
            # Update visual cues in state
            if "scenes" in state:
                for scene in state["scenes"]:
                    # scene might be a dict or a Scene object
                    sid = scene.get("scene_id") if isinstance(scene, dict) else getattr(scene, "scene_id", None)
                    if str(sid) == scene_id:
                        dialogue = scene.get("dialogue", []) if isinstance(scene, dict) else getattr(scene, "dialogue", [])
        # ─────────────────────────────────────────────────────────────────────
        # TARGET: AUDIO_FX (Post-Proc Only)
        # ─────────────────────────────────────────────────────────────────────
        elif target == "audio_fx":
            logger.info("🔊 [Phase 5] Routing to Audio Post-Production Suite...")
            state["post_proc_map"] = {
                intent.get("scope", "global"): {
                    **intent.get("parameters", {}),
                    "target": "audio_fx"
                }
            }
            state["skip_all_gen"] = True
            return {"data": state, "next_step": "phase2_partial"}

        # ─────────────────────────────────────────────────────────────────────
        # TARGET: VIDEO_FX (Post-Proc Only)
        # ─────────────────────────────────────────────────────────────────────
        elif target == "video_fx":
            logger.info("🎞️ [Phase 5] Routing to Video Post-Production Suite...")
            state["post_proc_map"] = {
                intent.get("scope", "global"): {
                    **intent.get("parameters", {}),
                    "target": "video_fx"
                }
            }
            state["skip_all_gen"] = True
            return {"data": state, "next_step": "phase2_partial"}

        # ─────────────────────────────────────────────────────────────────────
        # TARGET: AUDIO (Regenerative)
        # ─────────────────────────────────────────────────────────────────────
        elif target == "audio":
            # Re-run Voice Synth
            logger.info("🎤 [Phase 5] Re-running Voice Synth...")
            
            # 1. Update state with intent parameters
            scope = intent.get("scope", "")
            params = intent.get("parameters", {})
            
            # If scoped to a character, update character_db
            if scope.startswith("character:"):
                char_name = scope.split(":")[-1]
                logger.info(f"👤 [Phase 5] Updating voice for character: {char_name}")
                if "character_db" in state:
                    for char in state["character_db"]:
                        if char.get("name") == char_name:
                            # Apply gender/voice/speed changes
                            if "gender" in params: char["gender"] = params["gender"]
                            if "voice" in params: char["edge_voice"] = params["voice"]
                            if "speed" in params: char["speed"] = params["speed"]
                            # For male/female specific requests
                            if "male" in str(params).lower(): char["gender"] = "male"
                            if "female" in str(params).lower(): char["gender"] = "female"
            
            # If scoped to a scene, we could update dialogue emotion
            elif scope.startswith("scene:"):
                scene_id = scope.split(":")[-1]
                logger.info(f"🎬 [Phase 5] Updating voice parameters for scene: {scene_id}")
                if "scenes" in state:
                    for scene in state["scenes"]:
                        if str(scene.get("scene_id")) == scene_id:
                            for line in scene.get("dialogue", []):
                                if "emotion" in params: line["emotion"] = params["emotion"]
                                if "tone" in params: line["emotion"] = params["tone"]

            # Trigger Phase 2 with skip_video=True
            state["skip_video"] = True
            state["skip_all_gen"] = False
            return {"data": state, "next_step": "phase2_partial"}
            
        # ─────────────────────────────────────────────────────────────────────
        # TARGET: VIDEO_FRAME (Regenerative)
        # ─────────────────────────────────────────────────────────────────────
        elif target == "video_frame":
            # Re-run Image Generation for specific scene
            scope = intent.get("scope", "")
            params = intent.get("parameters", {})
            scene_id = scope.split(":")[-1]
            logger.info(f"🖼️ [Phase 5] Re-running Video Gen for Scene {scene_id}...")
            
            # Update visual cues in state
            if "scenes" in state:
                for scene in state["scenes"]:
                    # scene might be a dict or a Scene object
                    sid = scene.get("scene_id") if isinstance(scene, dict) else getattr(scene, "scene_id", None)
                    if str(sid) == scene_id:
                        dialogue = scene.get("dialogue", []) if isinstance(scene, dict) else getattr(scene, "dialogue", [])
                        for line in dialogue:
                            for key, val in params.items():
                                line["visual_cue"] = f"{line.get('visual_cue', '')}, {key}: {val}".strip(", ")

            # We'll trigger a Phase 2 run filtered by scene_id
            state["skip_all_gen"] = False
            return {"data": state, "next_step": "phase2_partial", "scene_id": int(scene_id)}
            
        elif target == "video":
            # Re-run Compositor
            logger.info("🎬 [Phase 5] Re-running Compositor...")
            from agents.video_agent.agent import compositor_node
            # Update state with parameters (e.g. subtitles=False)
            if intent.get("intent") == "remove_subtitles":
                os.environ["COMPOSITOR_SUBTITLES"] = "0"
            
            s_state = StudioState(**state)
            result = compositor_node(s_state)
            return {"data": result, "next_step": "completed"}
            
        return {"data": state, "error": "Unknown target"}
    except Exception as e:
        logger.error(f"❌ Edit execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
