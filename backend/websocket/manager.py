import json
import asyncio
from typing import List
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        # Always refresh — the loop reference stays valid for the server lifetime.
        self.loop = asyncio.get_running_loop()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        try:
            self.active_connections.remove(websocket)
        except ValueError:
            pass  # already removed, ignore

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                # Client disconnected mid-broadcast — clean up silently.
                self.disconnect(connection)

    async def send_progress(self, phase: str, step: str, status: str, details: str = ""):
        payload = {
            "phase": phase,
            "step": step,
            "status": status,
            "details": details
        }
        await self.broadcast(json.dumps(payload))

progress_manager = ConnectionManager()
