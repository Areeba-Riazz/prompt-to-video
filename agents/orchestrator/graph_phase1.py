"""
Orchestrator — graph.py
Phase 1 LangGraph workflow (Writer's Room / PROJECT MONTAGE Phase 1).
Migrated from root-level graph.py.
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from shared.schemas.state import MontageState
from agents.edit_agent.agent import validator_node, hitl_node
from agents.edit_agent.executor import failure_terminal_node
from agents.story_agent.agent import scriptwriter_node, character_node, image_node, memory_commit_node
from agents.orchestrator.state import route_input, route_after_validator, route_after_hitl
from mcp.tool_registry import registry as mcp_registry


def mode_selector_node(state: MontageState) -> dict:
    """Initial node to set the start of the process."""
    return {"current_agent": "Supervisor"}


def montage_workflow():
    """Initializes and compiles the Phase 1 PROJECT MONTAGE StateGraph."""
    workflow = StateGraph(MontageState)

    # Nodes
    workflow.add_node("Mode_selector_node", mode_selector_node)
    workflow.add_node("Validator_node", validator_node)
    workflow.add_node("Scriptwriter_node", scriptwriter_node)
    workflow.add_node("Hitl_node", hitl_node)
    workflow.add_node("Character_node", character_node)
    workflow.add_node("Image_node", image_node)
    workflow.add_node("Memory_commit_node", memory_commit_node)
    workflow.add_node("Failure_terminal_node", failure_terminal_node)

    # Entry point
    workflow.set_entry_point("Mode_selector_node")

    # Edges
    workflow.add_conditional_edges(
        "Mode_selector_node",
        route_input,
        {"validator": "Validator_node", "scriptwriter": "Scriptwriter_node"},
    )
    workflow.add_conditional_edges(
        "Validator_node",
        route_after_validator,
        {"hitl": "Hitl_node", "end": "Failure_terminal_node"},
    )
    workflow.add_edge("Scriptwriter_node", "Hitl_node")
    workflow.add_conditional_edges(
        "Hitl_node",
        route_after_hitl,
        {"character": "Character_node", "end": "Failure_terminal_node"},
    )
    workflow.add_edge("Character_node", "Image_node")
    workflow.add_edge("Image_node", "Memory_commit_node")
    workflow.add_edge("Memory_commit_node", END)
    workflow.add_edge("Failure_terminal_node", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory, interrupt_before=["Hitl_node"])
