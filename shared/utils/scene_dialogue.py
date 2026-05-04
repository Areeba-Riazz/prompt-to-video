"""Scene manifest dialogue helpers (Phase 2)."""

from __future__ import annotations

from typing import Any, Dict, List


def dialogue_line_speaker_counts(dialogue: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for line in dialogue or []:
        spk = (line.get("speaker") or "").strip()
        if spk:
            counts[spk] = counts.get(spk, 0) + 1
    return counts


def primary_speaker_from_dialogue(dialogue: List[Dict[str, Any]]) -> str:
    """Character with the most dialogue lines in this scene (ties: lexicographic max)."""
    counts = dialogue_line_speaker_counts(dialogue)
    if not counts:
        return ""
    return max(counts.keys(), key=lambda k: (counts[k], k))
