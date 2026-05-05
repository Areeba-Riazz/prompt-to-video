"""
Orchestrator — workflow.py
Phase 2 LangGraph workflow (Studio Floor).
Parallel multi-agent execution with Send() API for scene-level branching.
Migrated from root-level graph_phase2.py.
"""

from langgraph.graph import END, StateGraph
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StudioFloor")

from shared.schemas.phase2_state import StudioState
from agents.audio_agent.agent import voice_synth_node
from agents.video_agent.agent import (
    compositor_node,
    face_swap_node,
    lip_sync_node,
    memory_commit_node,
    video_gen_node,
)
from agents.orchestrator.state import route_after_parse, route_video_branches


def scene_parser_node(state: StudioState) -> dict:
    """
    Reads scene_manifest.json via MCP get_task_graph tool.
    Produces structured scene_jobs list consumed by all downstream workers.
    """
    logger.info("📑 [Scene Parser] Analyzing manifest and decomposing tasks...")
    registry = _get_registry()
    manifest_path = state.get("scene_manifest_path", os.path.join(os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1"), "scene_manifest.json"))
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))

    if not os.path.exists(manifest_path):
        return {
            "status": "failed",
            "errors": [f"Missing scene manifest: {manifest_path}"],
            "current_agent": "SceneParser",
        }

    task_graph_result = registry.invoke("get_task_graph", {
        "manifest_path": manifest_path,
        "parallel": True,
    })

    tasks = task_graph_result.get("tasks", [])
    scene_id_filter = state.get("scene_id_filter")

    scene_jobs = [
        {"scene_id": task["scene_id"], "scene": task, "task": task}
        for task in tasks
        if scene_id_filter is None or int(task["scene_id"]) == scene_id_filter
    ]

    return {
        "scenes": tasks,
        "task_graph": tasks,
        "scene_jobs": scene_jobs,
        "status": "processing",
        "current_agent": "SceneParser",
        "task_logs": [{
            "agent": "SceneParser",
            "event": "task_graph_created",
            "total_scenes": len(tasks),
            "parallel_enabled": task_graph_result.get("parallel_enabled", True),
        }],
    }


from agents.post_proc_agent.agent import post_proc_node


def failure_terminal_node(state: StudioState) -> StudioState:
    """Absorbs pipeline failures gracefully."""
    errors = state.get("errors", [])
    print(f"[Graph] Pipeline halted. Errors: {errors}")
    return state


def _get_registry():
    from mcp.tool_registry import registry
    return registry


def studio_floor_workflow():
    """
    Builds and compiles the Phase 2+3 LangGraph studio workflow.

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
        END   ← Phase 3 compositor is triggered on demand via /api/phase2/compose
    """
    workflow = StateGraph(StudioState)

    workflow.add_node("Scene_parser_node", scene_parser_node)
    workflow.add_node("Voice_synth_node", voice_synth_node)
    workflow.add_node("Video_gen_node", video_gen_node)
    workflow.add_node("Face_swap_node", face_swap_node)
    workflow.add_node("Lip_sync_node", lip_sync_node)
    workflow.add_node("Post_proc_node", post_proc_node)
    workflow.add_node("Memory_commit_node", memory_commit_node)
    workflow.add_node("Failure_terminal_node", failure_terminal_node)

    workflow.set_entry_point("Scene_parser_node")

    workflow.add_conditional_edges(
        "Scene_parser_node",
        route_after_parse,
        {
            "voice": "Voice_synth_node", 
            "post_proc": "Post_proc_node",
            "end": "Failure_terminal_node"
        },
    )
    workflow.add_conditional_edges(
        "Voice_synth_node",
        route_video_branches,
        ["Video_gen_node"],
    )
    workflow.add_edge("Video_gen_node", "Face_swap_node")
    workflow.add_edge("Face_swap_node", "Lip_sync_node")
    workflow.add_edge("Lip_sync_node", "Post_proc_node")
    workflow.add_edge("Post_proc_node", "Memory_commit_node")
    workflow.add_edge("Memory_commit_node", END)
    workflow.add_edge("Failure_terminal_node", END)

    return workflow.compile()
