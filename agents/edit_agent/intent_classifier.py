"""
Edit Agent — Intent Classifier
Routing logic that determines which branch the LangGraph workflow takes
based on the user's chosen input mode (manual vs auto).
"""

from shared.schemas.state import MontageState


def route_input(state: MontageState) -> str:
    """
    Routing function to select between Manual Script Upload or Auto Generation.
    Returns 'validator' for manual mode, 'scriptwriter' for auto mode.
    """
    if state.get("input_mode") == "manual":
        return "validator"
    return "scriptwriter"
