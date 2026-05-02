"""
MCP Tool Registry — Phase 2
Formal dynamic tool registry. Agents call discover() at runtime — never import
tool functions directly. This satisfies the assignment's 'no hardcoding' contract.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable
    tags: List[str] = field(default_factory=list)


class MCPRegistry:
    """
    Dynamic MCP tool registry.
    Agents discover and invoke tools by name at runtime.
    """

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}

    def register(self, tool: MCPTool) -> None:
        """Register an MCP tool in the registry."""
        self._tools[tool.name] = tool
        print(f"[MCP] Registered tool: {tool.name}")

    def discover(self, tag_filter: Optional[str] = None) -> Dict[str, MCPTool]:
        """Return all tools, optionally filtered by tag."""
        if tag_filter:
            return {k: v for k, v in self._tools.items() if tag_filter in v.tags}
        return dict(self._tools)

    def invoke(self, tool_name: str, inputs: Dict[str, Any]) -> Any:
        """Invoke a tool by name with structured input dict."""
        if tool_name not in self._tools:
            raise ValueError(f"[MCP] Tool '{tool_name}' not found in registry.")
        tool = self._tools[tool_name]
        print(f"[MCP] Invoking: {tool_name} with inputs: {list(inputs.keys())}")
        return tool.handler(**inputs)

    def get_schema(self, tool_name: str) -> Dict[str, Any]:
        """Return the input schema for a given tool (for agent introspection)."""
        if tool_name not in self._tools:
            raise ValueError(f"[MCP] Tool '{tool_name}' not found.")
        return self._tools[tool_name].input_schema

    def list_tools(self) -> List[str]:
        """Return a list of all registered tool names."""
        return list(self._tools.keys())


# Singleton registry instance — all agents share this
registry = MCPRegistry()
