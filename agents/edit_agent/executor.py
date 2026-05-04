"""
Edit Agent — Executor
Terminal node for graceful pipeline failure exits.
"""

from shared.schemas.state import MontageState


def failure_terminal_node(state: MontageState) -> MontageState:
    """Terminal node used for graceful failure exits."""
    print("--- [Workflow] Terminated due to validation/review failure ---")
    return state
