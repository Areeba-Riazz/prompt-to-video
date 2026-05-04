from typing import Any, Dict
from mcp.base_tool import BaseTool

class SubtitleTool(BaseTool):
    @property
    def name(self) -> str:
        return "subtitle_tool"

    @property
    def description(self) -> str:
        return "Handles subtitle generation and hardcoding."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {"video_path": "str — path to video"}

    @property
    def tags(self) -> list[str]:
        return ["video", "subtitle"]

    def execute(self, **kwargs) -> Any:
        return {"ok": True, "status": "Not Implemented"}
