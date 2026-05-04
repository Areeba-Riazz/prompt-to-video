import traceback
from typing import Any, Dict
from mcp.base_tool import BaseTool

class ToolExecutor:
    """Safely executes an MCP tool, handling errors and logging."""

    @staticmethod
    def execute(tool: BaseTool, inputs: Dict[str, Any]) -> Any:
        print(f"[MCP] Invoking: {tool.name} with inputs: {list(inputs.keys())}")
        try:
            return tool.execute(**inputs)
        except Exception as e:
            print(f"[MCP Error] Tool '{tool.name}' failed: {e}")
            traceback.print_exc()
            return {"ok": False, "error": str(e), "status": "failed", "tool": tool.name}
