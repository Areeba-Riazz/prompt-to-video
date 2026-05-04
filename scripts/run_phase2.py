"""
Phase 2 Entry Point — main_phase2.py
Registers all MCP tools, loads Phase 1 outputs, and runs the Studio Floor workflow.
"""

import argparse
import json
import os
import sys

# Inject root directory into sys.path to allow imports from mcp and agents
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from dotenv import load_dotenv

# Always load repo-root .env (cwd-independent). Matches backend/app.py.
load_dotenv(os.path.join(ROOT_DIR, ".env"))


def run_studio_floor(
    scene_manifest_path: str = None,
    character_db_path: str = None,
    output_root: str = None,
    scene_id_filter: int = None,
):
    if scene_manifest_path is None:
        scene_manifest_path = os.path.join(os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1"), "scene_manifest.json")
    if character_db_path is None:
        character_db_path = os.path.join(os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1"), "character_db.json")
    if output_root is None:
        output_root = os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2")
    # ── Step 1: Register all MCP tools ──────────────────────────────────────
    from mcp.tool_registry import register_all_tools
    register_all_tools()

    # ── Step 2: Load Phase 1 outputs ────────────────────────────────────────
    from agents.orchestrator.graph_phase2 import studio_floor_workflow

    character_db: list = []
    if os.path.exists(character_db_path):
        with open(character_db_path, encoding="utf-8") as f:
            data = json.load(f)
            # character_db.json has {"characters": [...]}
            character_db = data.get("characters", data) if isinstance(data, dict) else data
        print(f"[Main] Loaded {len(character_db)} character(s) from {character_db_path}")
    else:
        print(f"[Main] Warning: character_db not found at {character_db_path}")

    # ── Step 3: Build initial state ──────────────────────────────────────────
    print("=== PROJECT MONTAGE: PHASE 2 STARTING ===")
    app = studio_floor_workflow()

    initial_state = {
        "scene_manifest_path": scene_manifest_path,
        "output_root": output_root,
        "character_db": character_db,
        "scene_id_filter": scene_id_filter,
        "scenes": [],
        "task_graph": [],
        "scene_jobs": [],
        "audio_tracks": [],
        "video_tracks": [],
        "face_swaps": [],
        "final_scenes": [],
        "task_logs": [],
        "status": "processing",
        "errors": [],
        "current_agent": "Entry",
    }

    # ── Step 4: Run the workflow ─────────────────────────────────────────────
    final_state = app.invoke(initial_state)
    status = final_state.get("status", "processing")
    if status not in ("failed", "completed"):
        status = "completed" if final_state.get("final_scenes") else "processing"

    # ── Step 5: Save summary ─────────────────────────────────────────────────
    os.makedirs(output_root, exist_ok=True)
    summary_path = os.path.join(output_root, "phase2_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "status": final_state.get("status"),
                "resolved_status": status,
                "errors": final_state.get("errors", []),
                "task_graph_nodes": len(final_state.get("task_graph", [])),
                "audio_tracks": final_state.get("audio_tracks", []),
                "video_tracks": final_state.get("video_tracks", []),
                "face_swaps": final_state.get("face_swaps", []),
                "final_scenes": final_state.get("final_scenes", []),
            },
            f,
            indent=2,
        )

    print(f"=== PROJECT MONTAGE: PHASE 2 {status.upper()} ===")
    print(f"Artifacts saved under: ./{output_root}")
    print(f"Summary:               {summary_path}")

    final_scenes = final_state.get("final_scenes", [])
    if final_scenes:
        print(f"Final scenes produced: {len(final_scenes)}")
        for sc in final_scenes:
            print(f"  Scene {sc.get('scene_id'):02d} -> {sc.get('final_video_path')}")

    if final_state.get("errors"):
        print("Errors encountered:")
        for err in final_state["errors"]:
            print(f"  - {err}")


if __name__ == "__main__":
    phase1_dir = os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1")
    phase2_dir = os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2")

    parser = argparse.ArgumentParser(description="Run Project Montage Phase 2 (Studio Floor).")
    parser.add_argument(
        "--manifest", default=os.path.join(phase1_dir, "scene_manifest.json"),
        help="Path to Phase 1 scene manifest JSON"
    )
    parser.add_argument(
        "--chardb", default=os.path.join(phase1_dir, "character_db.json"),
        help="Path to Phase 1 character database JSON"
    )
    parser.add_argument(
        "--out", default=phase2_dir,
        help="Output folder for phase 2 artifacts",
    )
    parser.add_argument(
        "--scene-id", type=int, default=None,
        help="Run only a specific scene ID",
    )
    args = parser.parse_args()

    run_studio_floor(
        scene_manifest_path=args.manifest,
        character_db_path=args.chardb,
        output_root=args.out,
        scene_id_filter=args.scene_id,
    )
