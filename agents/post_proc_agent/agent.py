import os
import logging
from typing import Any, Dict, List, Optional
from shared.schemas.phase2_state import StudioState

logger = logging.getLogger("PostProcAgent")

def _get_registry():
    from mcp.tool_registry import registry
    return registry

def post_proc_node(state: StudioState) -> dict:
    """
    Modular Post-Production Agent.
    Applies fine-grained FX (pitch, brightness, etc.) to existing assets.
    """
    from agents.edit_agent import edit_execution as edit_ex

    registry = _get_registry()
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    post_proc_map = state.get("post_proc_map", {})
    
    if not post_proc_map:
        return {}

    logger.info(f"🎨 [PostProc] Applying {len(post_proc_map)} effect(s)...")
    final_scenes = state.get("final_scenes", []) or []
    # Post-proc-only LangGraph runs skip upstream nodes; hydrate from disk so we do not
    # rely on initial_state injection (which would duplicate under operator.add reducers).
    if not final_scenes:
        final_scenes = edit_ex.hydrate_final_scenes_for_post_proc(output_root)
    logs = []

    # Ensure post-processed dir exists
    pp_dir = os.path.join(output_root, "post_processed")
    os.makedirs(pp_dir, exist_ok=True)

    updated_finals = []

    for scene_item in final_scenes:
        scene_id = scene_item["scene_id"]
        video_path = scene_item.get("final_video_path")
        audio_path = scene_item.get("audio_path")
        
        # Check for scene-specific effects
        scene_key = f"scene:{scene_id}"
        global_key = "global"
        
        scene_fx = post_proc_map.get(scene_key, {})
        global_fx = post_proc_map.get(global_key, {})
        
        # Merge global and scene-specific FX (scene overrides global)
        merged_fx = {**global_fx, **scene_fx}
        
        if not merged_fx:
            updated_finals.append(scene_item)
            continue

        # 1. Audio FX
        current_audio = audio_path
        if any(k in merged_fx for k in ["pitch", "speed", "volume", "filter_type"]):
            logger.info(f"🔊 [PostProc] Applying Audio FX to Scene {scene_id}...")
            fx_audio_path = os.path.join(pp_dir, f"scene_{scene_id}_fx.wav")
            res = registry.invoke("audio_fx_tool", {
                "input_path": current_audio,
                "output_path": fx_audio_path,
                "pitch": merged_fx.get("pitch", 1.0),
                "speed": merged_fx.get("speed", 1.0),
                "volume": merged_fx.get("volume", 1.0),
                "filter_type": merged_fx.get("filter_type") if merged_fx.get("target") == "audio_fx" else None
            })
            if res.get("ok"):
                current_audio = fx_audio_path
                logs.append({"agent": "PostProc", "scene_id": scene_id, "event": "audio_fx_applied"})
            else:
                logger.error(f"Audio FX failed: {res.get('error')}")

        # 2. Video FX
        current_video = video_path
        if any(k in merged_fx for k in ["brightness", "contrast", "saturation", "gamma", "filter_type"]):
            logger.info(f"🎞️ [PostProc] Applying Video FX to Scene {scene_id}...")
            fx_video_path = os.path.join(pp_dir, f"scene_{scene_id}_fx.mp4")
            res = registry.invoke("video_fx_tool", {
                "input_path": current_video,
                "output_path": fx_video_path,
                "brightness": merged_fx.get("brightness", 0.0),
                "contrast": merged_fx.get("contrast", 1.0),
                "saturation": merged_fx.get("saturation", 1.0),
                "gamma": merged_fx.get("gamma", 1.0),
                "filter_type": merged_fx.get("filter_type") if merged_fx.get("target") == "video_fx" else None
            })
            if res.get("ok"):
                current_video = fx_video_path
                logs.append({"agent": "PostProc", "scene_id": scene_id, "event": "video_fx_applied"})
            else:
                logger.error(f"Video FX failed: {res.get('error')}")

        updated_finals.append({
            **scene_item,
            "final_video_path": current_video,
            "audio_path": current_audio,
            "post_processed": True
        })

    return {"final_scenes": updated_finals, "task_logs": logs}
