"""
Edit Agent — Planner
Conditional routing functions used after the validator and HITL nodes
to determine whether the workflow continues or terminates.
"""

from shared.schemas.state import MontageState


def route_after_validator(state: MontageState) -> str:
    """
    Stop the workflow if manual script validation fails.
    Returns 'end' on failure, 'hitl' on success.
    """
    if state.get("status") == "failed":
        return "end"
    return "hitl"


def route_after_hitl(state: MontageState) -> str:
    """
    Only continue when HITL approved the script.
    Returns 'end' on rejection, 'character' on approval.
    """
    if state.get("status") == "failed":
        return "end"
    return "character"
