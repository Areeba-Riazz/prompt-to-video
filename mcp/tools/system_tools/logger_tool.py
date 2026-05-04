from typing import Any, Dict
from mcp.base_tool import BaseTool

class LoggerTool(BaseTool):
    @property
    def name(self) -> str:
        return "logger_tool"

    @property
    def description(self) -> str:
        return "Handles system wide logging."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {"message": "str — log message"}

    @property
    def tags(self) -> list[str]:
        return ["system", "logger"]

    def execute(self, **kwargs) -> Any:
        return {"ok": True, "status": "Not Implemented"}
