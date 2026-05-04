"""
Story Agent — Planner
Holds all fallback scene data and the scene-to-raw-script formatter.
Used by ScriptwriterAgent when the LLM is unavailable or returns unparseable output.
"""

from shared.schemas.state import Scene


def fallback_scenes(prompt: str) -> list:
    """
    Returns a hardcoded list of cinematic Scene objects as a safe fallback
    when the LLM call fails or returns invalid JSON.
    """
    topic = (prompt or "A hopeful futuristic journey through a luminous smart city").strip()
    return [
        Scene(
            scene_id=1,
            location="EXT. SKYBRIDGE GARDEN DISTRICT - NEON EVENING",
            characters=["Kael", "Sora"],
            dialogue=[
                {
                    "speaker": "Kael",
                    "line": f"Tonight we make this city feel alive again. {topic}",
                    "visual_cue": (
                        "Vibrant cyan, pink, and gold reflections across wet glass walkways, "
                        "elegant cinematic glow"
                    ),
                },
                {
                    "speaker": "Sora",
                    "line": "Then let's make every frame unforgettable.",
                    "visual_cue": (
                        "Close-up with radiant magenta rim light, soft bloom, "
                        "warm smile, premium fashion look"
                    ),
                },
            ],
        ),
        Scene(
            scene_id=2,
            location="INT. AURORA ARCHIVE ATRIUM - NIGHT",
            characters=["Kael", "Sora", "Warden AI"],
            dialogue=[
                {
                    "speaker": "Warden AI",
                    "line": "Creative access granted. Curating visual symphony.",
                    "visual_cue": (
                        "Floating holographic petals in amber and cyan, "
                        "mirrored marble floor, elegant light trails"
                    ),
                },
                {
                    "speaker": "Sora",
                    "line": "Perfect. Let's turn memory into color and music.",
                    "visual_cue": (
                        "Low-angle fashion portrait, vibrant teal-gold split lighting, "
                        "airy cinematic haze"
                    ),
                },
            ],
        ),
        Scene(
            scene_id=3,
            location="EXT. PANORAMIC ROOFTOP STAGE - GOLDEN BLUE DAWN",
            characters=["Kael", "Sora"],
            dialogue=[
                {
                    "speaker": "Kael",
                    "line": "The real prize was giving everyone a brighter story.",
                    "visual_cue": (
                        "Radiant dawn gradient of cobalt and gold, crisp silhouettes, "
                        "cinematic lens flares, celebratory mood"
                    ),
                },
                {
                    "speaker": "Sora",
                    "line": "And now the whole skyline feels like a heartbeat.",
                    "visual_cue": (
                        "Wide anamorphic frame, vivid warm highlights, "
                        "gentle cool shadows, uplifting atmosphere"
                    ),
                },
            ],
        ),
    ]


def scenes_to_raw_script(scenes: list) -> str:
    """Converts a list of Scene objects into a plain-text screenplay format."""
    lines = []
    for scene in scenes:
        lines.append(scene.location)
        lines.append("[Cinematic action beat and staging]")
        for turn in scene.dialogue:
            lines.append(f"{turn['speaker'].upper()}: {turn['line']}")
        lines.append("")
    return "\n".join(lines).strip()
