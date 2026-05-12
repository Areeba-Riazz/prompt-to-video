from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import logging
import os
import json
import shutil
import uuid

from agents.orchestrator.graph_phase1 import montage_workflow
from shared.schemas.state import MontageState
from shared.repo_paths import resolve_from_repo

router = APIRouter()
graph = montage_workflow()
logger = logging.getLogger("Phase1Route")


def _phase1_output_dir() -> str:
    return resolve_from_repo(os.environ.get("PHASE1_OUTPUT_DIR", os.path.join("data", "outputs", "phase1")))


def _clear_phase1_outputs() -> None:
    """
    Delete all Phase 1 generated artifacts so a new run starts clean:
      • image_assets/  — character portrait PNGs
      • character_db.json
      • scene_manifest.json
    Phase 2 / Phase 3 outputs are NOT touched here.
    """
    p1 = _phase1_output_dir()
    img_dir = os.path.join(p1, "image_assets")
    if os.path.isdir(img_dir):
        shutil.rmtree(img_dir, ignore_errors=True)
        logger.info("Cleared image_assets for new Phase 1 run.")
    for fname in ("character_db.json", "scene_manifest.json"):
        fp = os.path.join(p1, fname)
        if os.path.exists(fp):
            os.remove(fp)
            logger.info("Removed stale %s", fname)

class PromptRequest(BaseModel):
    prompt: str

class HitlApproveRequest(BaseModel):
    approved: bool

# Store the current thread_id globally for single-user local testing
CURRENT_THREAD_ID = "montage-session-default"

@router.post("/run")
async def run_phase1(req: PromptRequest):
    global CURRENT_THREAD_ID
    CURRENT_THREAD_ID = str(uuid.uuid4())

    # Wipe stale images and Phase 1 artifacts before starting fresh.
    _clear_phase1_outputs()

    try:
        config = {"configurable": {"thread_id": CURRENT_THREAD_ID}}
        # Reset state for a new run
        state = MontageState(
            user_prompt=req.prompt,
            input_mode="auto", # auto routes to Scriptwriter_node, then automatically to Hitl_node
            hitl_approved=False
        )
        
        # Invoke the graph. Since memory checkpointer is attached, it will interrupt at hitl_node
        for _ in graph.stream(state, config=config):
            pass 
            
        current_state = graph.get_state(config)
        
        # If the graph stopped at Hitl_node
        if "Hitl_node" in current_state.next:
            return {
                "data": {
                    "status": "awaiting_hitl",
                    "script": {"scenes": current_state.values.get("scenes", [])} 
                    # The frontend Phase1.tsx expects `data.script.scenes` for HITL display
                    # Or raw_script. Let's pass the raw scenes object down.
                }
            }
        
        return {"data": current_state.values}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hitl/approve")
def approve_hitl(req: HitlApproveRequest):
    """
    Run as a plain `def` (NOT async) so FastAPI dispatches it to a thread-pool
    worker. This keeps the event loop free to send WebSocket progress broadcasts
    while character_node and image_node are executing (which can take minutes).
    An async def here would freeze the loop and silently drop all WS messages.
    """
    global CURRENT_THREAD_ID
    try:
        config = {"configurable": {"thread_id": CURRENT_THREAD_ID}}

        # Update state with human decision
        graph.update_state(config, {"hitl_approved": req.approved})

        # Resume graph execution — blocks this thread, not the event loop
        for _ in graph.stream(None, config=config):
            pass

        final_state = graph.get_state(config).values

        if final_state.get("status") == "failed":
            raise HTTPException(status_code=400, detail="Pipeline failed or rejected.")

        # Frontend expects: { script: {scenes: [...]}, characters: [...] }
        return {
            "data": {
                "script": {"scenes": final_state.get("scenes", [])},
                "characters": final_state.get("characters", [])
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/character-image/{name}")
async def get_character_image(name: str):
    import re
    # Match the sanitization used in ImageSynthesizer
    safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    img_dir = os.path.join(_phase1_output_dir(), "image_assets")

    # 1. Exact match
    img_path = os.path.join(img_dir, f"{safe_name}.png")
    if os.path.exists(img_path):
        return FileResponse(img_path)

    # 2. Prefix match — e.g. "suspect" → "suspect_alex.png"
    if os.path.isdir(img_dir):
        for fname in sorted(os.listdir(img_dir)):
            if fname.lower().startswith(safe_name + "_") and fname.lower().endswith(".png"):
                return FileResponse(os.path.join(img_dir, fname))

    # 3. Substring match — last resort so partial names still resolve
    if os.path.isdir(img_dir):
        for fname in sorted(os.listdir(img_dir)):
            if safe_name in fname.lower() and fname.lower().endswith(".png"):
                return FileResponse(os.path.join(img_dir, fname))

    raise HTTPException(status_code=404, detail=f"No image found for character {name!r}")

@router.get("/script")
async def get_phase1_script():
    """Serves the scene manifest generated in Phase 1."""
    path = os.path.join(_phase1_output_dir(), "scene_manifest.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Scene manifest not found. Run Phase 1 first.")
    with open(path, "r") as f:
        return {"data": json.load(f)}

@router.get("/characters")
async def get_phase1_characters():
    """Serves the character database generated in Phase 1."""
    path = os.path.join(_phase1_output_dir(), "character_db.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Character database not found. Run Phase 1 first.")
    with open(path, "r") as f:
        data = json.load(f)
        return {"data": data.get("characters", []) if isinstance(data, dict) else data}
