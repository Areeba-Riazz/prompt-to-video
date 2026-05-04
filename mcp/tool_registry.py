from typing import Any, Dict, List, Optional
from mcp.base_tool import BaseTool
from mcp.tool_executor import ToolExecutor

class MCPRegistry:
    """
    Dynamic MCP tool registry.
    Agents discover and invoke tools by name at runtime.
    """
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        print(f"[MCP] Registered tool: {tool.name}")

    def discover(self, tag_filter: Optional[str] = None) -> Dict[str, BaseTool]:
        if tag_filter:
            return {k: v for k, v in self._tools.items() if tag_filter in v.tags}
        return dict(self._tools)

    def invoke(self, tool_name: str, inputs: Dict[str, Any]) -> Any:
        if tool_name not in self._tools:
            raise ValueError(f"[MCP] Tool '{tool_name}' not found in registry.")
        tool = self._tools[tool_name]
        return ToolExecutor.execute(tool, inputs)

    def get_schema(self, tool_name: str) -> Dict[str, str]:
        if tool_name not in self._tools:
            raise ValueError(f"[MCP] Tool '{tool_name}' not found.")
        return self._tools[tool_name].input_schema

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    # --- Backward compatibility methods for Phase 1 ---
    def call_tool(self, name: str, **kwargs) -> Any:
        """Phase 1 backwards compatibility."""
        return self.invoke(name, kwargs)

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": str(tool.input_schema),
            }
            for tool in self._tools.values()
        ]

def register_all_tools():
    """
    Register all Phase 2 MCP tools.
    Agents call registry.discover() to find tools at runtime.
    """
    from mcp.tools.audio_tools.tts_tool import VoiceSynthesisTool
    from mcp.tools.video_tools.video_gen_tool import VideoGenerationTool
    from mcp.tools.video_tools.lip_sync_tool import LipSyncTool
    from mcp.tools.video_tools.ffmpeg_tool import FFmpegTool
    from mcp.tools.vision_tools.image_gen_tool import ImageGenerationTool, QueryStockFootageTool
    from mcp.tools.vision_tools.face_swap_tool import FaceSwapTool
    from mcp.tools.vision_tools.identity_tool import IdentityValidatorTool
    from mcp.tools.llm_tools.text_generator import TextGeneratorTool
    from mcp.tools.system_tools.state_tool import MemoryCommitTool, TaskGraphTool

    registry.register(VoiceSynthesisTool())
    registry.register(VideoGenerationTool())
    registry.register(LipSyncTool())
    registry.register(FFmpegTool())
    registry.register(ImageGenerationTool())
    registry.register(QueryStockFootageTool())
    registry.register(FaceSwapTool())
    registry.register(IdentityValidatorTool())
    registry.register(TextGeneratorTool())
    registry.register(MemoryCommitTool())
    registry.register(TaskGraphTool())
    print(f"[MCP] Phase 2: {len(registry.discover())} tools registered successfully.")

# Global singleton instance
registry = MCPRegistry()
