import os
import sys

# Inject root directory into sys.path to allow imports when running directly
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routes.phase1 import router as phase1_router
from backend.routes.phase2 import router as phase2_router
from backend.websocket.manager import progress_manager
from fastapi import WebSocket, WebSocketDisconnect

from mcp.tool_registry import register_all_tools

# Initialize all MCP tools
register_all_tools()

app = FastAPI(title="Project Montage API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow Vite frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    print(f"🔌 [WebSocket] New connection attempt from {websocket.client}")
    try:
        await progress_manager.connect(websocket)
        print(f"✅ [WebSocket] Connection accepted: {websocket.client}")
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        print(f"❌ [WebSocket] Client disconnected: {websocket.client}")
        progress_manager.disconnect(websocket)
    except Exception as e:
        print(f"⚠️ [WebSocket] Error: {e}")
        try:
            progress_manager.disconnect(websocket)
        except:
            pass

app.include_router(phase1_router, prefix="/api/phase1", tags=["Phase 1"])
app.include_router(phase2_router, prefix="/api/phase2", tags=["Phase 2"])

if __name__ == "__main__":
    import uvicorn
    # Run the server on port 8000
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
