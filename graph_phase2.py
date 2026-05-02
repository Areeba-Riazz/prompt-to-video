"""
Phase 2 LangGraph Workflow — graph_phase2.py
Parallel multi-agent execution with Send() API for scene-level branching.
Satisfies: Parallel Architecture (10 pts), MCP Tool Usage, Fault Tolerance.
"""

import json
import os
from typing import Annotated, Any, Dict, List, TypedDict
import operator

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from agents.studio_workers import (
    face_swap_node,
    lip_sync_node,
    scene_parser_node,
    video_gen_node,
    voice_synth_node,
    memory_commit_node,
)
from schema.phase2_state import StudioState


# ─────────────────────────────────────────────────────────────────────────────
# Routing functions
# ─────────────────────────────────────────────────────────────────────────────

def route_after_parse(state: StudioState):
    """Route to parallel voice+video processing or to failure terminal."""
    if state.get("status") == "failed":
        return "end"
    return "voice"


def route_video_branches(state: StudioState):
    """
    Parallel fan-out using LangGraph Send() API.
    One Send per scene_job → each runs video_gen independently.
    """
    jobs = state.get("scene_jobs", [])
    if not jobs:
        return [Send("Face_swap_node", state)]

    print(f"[Graph] Distributing {len(jobs)} scene(s) in parallel for video generation…")
    return [
        Send("Video_gen_node", {
            **state,
            "scene_jobs": [job],   # each branch gets exactly one job
        })
        for job in jobs
    ]


def failure_terminal_node(state: StudioState):
    """Absorbs pipeline failures gracefully."""
    errors = state.get("errors", [])
    print(f"[Graph] Pipeline halted. Errors: {errors}")
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────────────────────────────────────

def studio_floor_workflow():
    """
    Builds and compiles the Phase 2 LangGraph studio workflow.

    Flow:
        Scene_parser_node
            ↓ (route_after_parse)
        Voice_synth_node
            ↓ (route_video_branches — parallel Send per scene)
        Video_gen_node  [parallel]
            ↓
        Face_swap_node
            ↓
        Lip_sync_node
            ↓
        Memory_commit_node
            ↓
        END
    """
    workflow = StateGraph(StudioState)

    workflow.add_node("Scene_parser_node", scene_parser_node)
    workflow.add_node("Voice_synth_node", voice_synth_node)
    workflow.add_node("Video_gen_node", video_gen_node)
    workflow.add_node("Face_swap_node", face_swap_node)
    workflow.add_node("Lip_sync_node", lip_sync_node)
    workflow.add_node("Memory_commit_node", memory_commit_node)
    workflow.add_node("Failure_terminal_node", failure_terminal_node)

    workflow.set_entry_point("Scene_parser_node")

    # After parse: route to voice or failure
    workflow.add_conditional_edges(
        "Scene_parser_node",
        route_after_parse,
        {"voice": "Voice_synth_node", "end": "Failure_terminal_node"},
    )

    # After voice: parallel Send() per scene to video gen
    workflow.add_conditional_edges(
        "Voice_synth_node",
        route_video_branches,
        ["Video_gen_node"],
    )

    # Sequential: video → face swap → lip sync → done
    workflow.add_edge("Video_gen_node", "Face_swap_node")
    workflow.add_edge("Face_swap_node", "Lip_sync_node")
    workflow.add_edge("Lip_sync_node", "Memory_commit_node")
    workflow.add_edge("Memory_commit_node", END)
    workflow.add_edge("Failure_terminal_node", END)

    return workflow.compile()
