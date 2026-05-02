"""
Task Graph Tool — MCP Tool: get_task_graph
Decomposes scene_manifest.json into parallelizable scene tasks.
Each task carries everything a scene worker needs to run independently.
"""

import json
from typing import Any, Dict, List


def _infer_emotion(visual_cues: str) -> str:
    """Infer dialogue emotion from scene visual cue text."""
    cue = visual_cues.lower()
    if any(w in cue for w in ["tense", "dramatic", "confrontation", "fierce", "battle"]):
        return "angry"
    if any(w in cue for w in ["warm", "gentle", "soft", "smile", "celebratory", "uplifting"]):
        return "happy"
    if any(w in cue for w in ["sad", "somber", "grief", "mournful", "tears"]):
        return "sad"
    if any(w in cue for w in ["dark", "fearful", "horror", "shock", "dread"]):
        return "fearful"
    return "neutral"


def get_task_graph(manifest_path: str, parallel: bool = True) -> Dict[str, Any]:
    """
    Reads scene_manifest.json and produces a structured task graph.

    Each task contains everything a scene worker needs to run independently.
    Satisfies the assignment's Task Graph-based Execution requirement.

    Args:
        manifest_path: Path to scene_manifest.json from Phase 1.
        parallel: Whether to enable parallel LangGraph Send() branching.

    Returns:
        Dict with 'total_scenes', 'parallel_enabled', and 'tasks' list.
    """
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    scenes = manifest.get("scenes", [])
    tasks: List[Dict[str, Any]] = []

    for idx, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", idx + 1)
        location = scene.get("location", "unknown")
        characters = scene.get("characters", [])
        dialogue = scene.get("dialogue", [])

        # Derive a top-level visual_cues string from scene-level field or
        # fall back to combining the first visual_cue from dialogue entries.
        visual_cues = scene.get("visual_cues", "")
        if not visual_cues and dialogue:
            visual_cues = dialogue[0].get("visual_cue", "")

        emotion = _infer_emotion(visual_cues)

        # Enrich each dialogue line with inferred emotion
        enriched_dialogue: List[Dict[str, Any]] = [
            {**line, "emotion": emotion} for line in dialogue
        ]

        tasks.append(
            {
                "scene_id": scene_id,
                "location": location,
                "characters": characters,
                "dialogue": enriched_dialogue,
                "visual_cues": visual_cues,
                "parallel": parallel,
            }
        )

    return {
        "total_scenes": len(tasks),
        "parallel_enabled": parallel,
        "tasks": tasks,
    }
