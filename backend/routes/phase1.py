from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os
import json
import uuid

from agents.orchestrator.graph_phase1 import montage_workflow
from shared.schemas.state import MontageState

router = APIRouter()
graph = montage_workflow()

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
    img_dir = os.path.join(os.getcwd(), "data", "outputs", "phase1", "image_assets")
    img_path = os.path.join(img_dir, f"{safe_name}.png")
    if os.path.exists(img_path):
        return FileResponse(img_path)
    raise HTTPException(status_code=404, detail=f"Image not found at {img_path}")

@router.get("/script")
async def get_phase1_script():
    """Serves the scene manifest generated in Phase 1."""
    path = os.path.join("data", "outputs", "phase1", "scene_manifest.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Scene manifest not found. Run Phase 1 first.")
    with open(path, "r") as f:
        return {"data": json.load(f)}

@router.get("/characters")
async def get_phase1_characters():
    """Serves the character database generated in Phase 1."""
    path = os.path.join("data", "outputs", "phase1", "character_db.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Character database not found. Run Phase 1 first.")
    with open(path, "r") as f:
        data = json.load(f)
        return {"data": data.get("characters", []) if isinstance(data, dict) else data}
