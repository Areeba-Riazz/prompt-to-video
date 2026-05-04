"""Phase 2 scene-level helpers: portrait pick order, primary speaker."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from shared.utils.media_paths import resolve_media_path
from shared.utils.scene_dialogue import primary_speaker_from_dialogue


def scene_reference_portrait(scene: Dict[str, Any], char_db: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """
    Pick one canonical portrait path for this scene: primary speaker first, then other characters.
    Paths are resolved against cwd / PHASE1_OUTPUT_DIR (see resolve_media_path).
    """
    primary = primary_speaker_from_dialogue(scene.get("dialogue") or [])
    names: List[str] = []
    if primary:
        names.append(primary)
    for c in scene.get("characters") or []:
        if isinstance(c, str) and c and c not in names:
            names.append(c)
    for name in names:
        entry = char_db.get(name) or {}
        resolved = resolve_media_path(entry.get("image_path"))
        if resolved:
            return resolved
    return None
