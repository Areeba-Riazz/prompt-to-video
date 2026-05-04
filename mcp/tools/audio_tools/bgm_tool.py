from typing import Any, Dict
from mcp.base_tool import BaseTool

class BGMTool(BaseTool):
    @property
    def name(self) -> str:
        return "bgm_tool"

    @property
    def description(self) -> str:
        return "Handles background music generation or selection."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {"mood": "str — the mood of the background music"}

    @property
    def tags(self) -> list[str]:
        return ["audio", "bgm"]

    def execute(self, **kwargs) -> Any:
        return {"ok": True, "status": "Not Implemented"}
