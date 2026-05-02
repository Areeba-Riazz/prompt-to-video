from langgraph.graph import StateGraph, END
from schema.state import MontageState
from agents.validation_worker import validator_node
from agents.script_worker import scriptwriter_node
from agents.creative_workers import character_node, image_node

def mode_selector_node(state: MontageState):
    """Initial node to set the start of the process."""
    return {"current_agent": "Supervisor"}

def route_input(state: MontageState):
    """Routing function to select between Manual Script Upload or Auto Generation."""
    if state["input_mode"] == "manual":
        return "validator"
    return "scriptwriter"

def route_after_validator(state: MontageState):
    """Stop the workflow if manual script validation fails."""
    if state.get("status") == "failed":
        return "end"
    return "hitl"

def hitl_node(state: MontageState):
    """Human-in-the-Loop checkpoint requiring explicit approval."""
    print(f"\n--- [HITL] WAITING FOR HUMAN REVIEW ---")
    print(f"Current Script Preview: {state.get('raw_script', '')[:300]}...")
    print("Approve this script to continue? (y/n)")

    auto_approve = False
    # Non-interactive environments can bypass prompt if explicitly configured.
    try:
        import os
        auto_approve = os.getenv("HITL_AUTO_APPROVE", "").lower() in {"1", "true", "yes", "y"}
    except Exception:
        auto_approve = False

    approved = False
    if auto_approve:
        approved = True
        print("--- [HITL] Auto-approved via HITL_AUTO_APPROVE ---")
    else:
        try:
            user_choice = input("> ").strip().lower()
            approved = user_choice in {"y", "yes"}
        except EOFError:
            approved = False

    if not approved:
        print("--- [HITL] Script rejected by reviewer. Stopping workflow. ---")
        return {
            "status": "failed",
            "errors": state.get("errors", []) + ["Script rejected at HITL checkpoint"],
            "current_agent": "HITL"
        }

    print("--- [HITL] Review approved: proceeding to synthesis ---")
    return {"current_agent": "HITL"}

def route_after_hitl(state: MontageState):
    """Only continue when HITL approved the script."""
    if state.get("status") == "failed":
        return "end"
    return "character"

def failure_terminal_node(state: MontageState):
    """Terminal node used for graceful failure exits."""
    print("--- [Workflow] Terminated due to validation/review failure ---")
    return state

def memory_commit_node(state: MontageState):
    """Final node to commit all results to persistent memory via MCP."""
    from tools.mcp_handler import mcp_registry
    print(f"--- [Memory Commit] Finalizing persistent records ---")
    mcp_registry.call_tool("commit_memory", key="final_manifest", data=state.get("scenes"))
    return {"status": "completed"}

def montage_workflow():
    """Initializes the PROJECT MONTAGE StateGraph."""
    workflow = StateGraph(MontageState)

    # Define Nodes (Matching Requirement List)
    workflow.add_node("Mode_selector_node", mode_selector_node)
    workflow.add_node("Validator_node", validator_node)
    workflow.add_node("Scriptwriter_node", scriptwriter_node)
    workflow.add_node("Hitl_node", hitl_node)
    workflow.add_node("Character_node", character_node)
    workflow.add_node("Image_node", image_node)
    workflow.add_node("Memory_commit_node", memory_commit_node)
    workflow.add_node("Failure_terminal_node", failure_terminal_node)

    # Define Conditional Edges (Routing)
    workflow.set_entry_point("Mode_selector_node")
    
    workflow.add_conditional_edges(
        "Mode_selector_node",
        route_input,
        {
            "validator": "Validator_node",
            "scriptwriter": "Scriptwriter_node"
        }
    )

    workflow.add_conditional_edges(
        "Validator_node",
        route_after_validator,
        {
            "hitl": "Hitl_node",
            "end": "Failure_terminal_node"
        }
    )

    workflow.add_edge("Scriptwriter_node", "Hitl_node")
    workflow.add_conditional_edges(
        "Hitl_node",
        route_after_hitl,
        {
            "character": "Character_node",
            "end": "Failure_terminal_node"
        }
    )
    workflow.add_edge("Character_node", "Image_node")
    workflow.add_edge("Image_node", "Memory_commit_node")
    workflow.add_edge("Memory_commit_node", END)
    workflow.add_edge("Failure_terminal_node", END)

    return workflow.compile()
