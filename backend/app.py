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

app.include_router(phase1_router, prefix="/api/phase1", tags=["Phase 1"])
app.include_router(phase2_router, prefix="/api/phase2", tags=["Phase 2"])

if __name__ == "__main__":
    import uvicorn
    # Run the server on port 8000
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=True)
