"""
Orchestrator — State
All routing / conditional-edge functions for both Phase 1 and Phase 2 graphs.
Kept here so graph.py and workflow.py stay clean and declarative.
"""

from shared.schemas.state import MontageState
from shared.schemas.phase2_state import StudioState
from agents.edit_agent.intent_classifier import route_input
from agents.edit_agent.planner import route_after_validator, route_after_hitl


def route_video_branches(state: StudioState):
    """
    Phase 2 parallel fan-out using LangGraph Send() API.
    One Send per scene_job → each runs video_gen independently.
    """
    from langgraph.types import Send

    jobs = state.get("scene_jobs", [])
    if not jobs:
        return [Send("Face_swap_node", state)]

    print(f"[Graph] Distributing {len(jobs)} scene(s) in parallel for video generation…")
    return [
        Send("Video_gen_node", {**state, "scene_jobs": [job]})
        for job in jobs
    ]


def route_after_parse(state: StudioState) -> str:
    """Route to parallel voice+video processing or to failure terminal."""
    if state.get("status") == "failed":
        return "end"
    return "voice"


# Re-export Phase 1 routing functions so orchestrator/graph.py can import
# everything it needs from a single place (this module).
__all__ = [
    "route_input",
    "route_after_validator",
    "route_after_hitl",
    "route_after_parse",
    "route_video_branches",
]
