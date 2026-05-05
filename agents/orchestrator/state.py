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
    If skip_video is True, we skip Video_gen_node and go straight to Face_swap_node.
    """
    from langgraph.types import Send

    jobs = state.get("scene_jobs", [])
    if not jobs:
        return [Send("Face_swap_node", state)]

    skip = state.get("skip_video", False)
    target_node = "Face_swap_node" if skip else "Video_gen_node"

    if skip:
        print(f"[Graph] skip_video=True: Bypassing video generation, going straight to {target_node}")

    return [
        Send(target_node, {**state, "scene_jobs": [job]})
        for job in jobs
    ]


def route_after_parse(state: StudioState) -> str:
    """Route to parallel voice+video processing, post-proc only, or to failure terminal."""
    if state.get("status") == "failed":
        return "end"
    if state.get("skip_all_gen"):
        return "post_proc"
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
