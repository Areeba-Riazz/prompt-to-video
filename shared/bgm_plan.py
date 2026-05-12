"""
Story-aware background music planning for Phase 3 compositor.

Uses scene locations, dialogue, visual cues, and optional user prompt heuristics
(no extra LLM call) to choose mood, Freesound search flavour, volume scale, and
whether to apply BGM at all.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, TypedDict


class BgmPlan(TypedDict, total=False):
    apply_bgm: bool
    mood: str
    freesound_boost: str
    volume_multiplier: float
    reason: str


MOODS = ("happy", "sad", "tense", "calm", "epic", "neutral")

# If any of these appear in aggregated story text + prompt, skip BGM entirely.
_NO_BGM_PHRASES = (
    "no background music",
    "no bgm",
    "without music",
    "silent film",
    "dialogue only",
    "no underscoring",
    "no score",
    "music off",
    "ambient silence",
)

# Softer bed when setting suggests intimacy / gravity.
_QUIET_SETTINGS = (
    "funeral",
    "hospital",
    "library",
    "confession",
    "therapy",
    "courtroom",
    "interrogation",
    "prison cell",
    "bedside",
    "wedding vow",  # often want soft not loud — still keep music
)

# (mood, (keyword, weight), ...)
_MOOD_KEYWORDS: List[tuple[str, tuple[tuple[str, float], ...]]] = [
    (
        "tense",
        (
            ("danger", 2.0),
            ("chase", 2.0),
            ("scream", 1.5),
            ("panic", 1.5),
            ("gun", 2.0),
            ("blood", 1.2),
            ("storm", 1.2),
            ("dark", 0.8),
            ("night", 0.6),
            ("hide", 1.0),
            ("running", 0.8),
            ("knife", 1.5),
            ("explosion", 1.8),
            ("deadline", 0.9),
        ),
    ),
    (
        "sad",
        (
            ("funeral", 2.5),
            ("tears", 1.5),
            ("goodbye", 1.2),
            ("death", 2.0),
            ("alone", 1.0),
            ("lost", 1.0),
            ("miss you", 1.5),
            ("sorry", 0.6),
            ("cry", 1.2),
            ("grief", 2.0),
            ("breakup", 1.3),
            ("regret", 1.2),
        ),
    ),
    (
        "happy",
        (
            ("celebration", 2.0),
            ("wedding", 1.5),
            ("party", 1.5),
            ("laugh", 1.2),
            ("joy", 1.5),
            ("victory", 1.3),
            ("birthday", 1.2),
            ("dance", 1.0),
            ("cheers", 1.0),
            ("reunion", 1.2),
        ),
    ),
    (
        "epic",
        (
            ("battle", 2.2),
            ("war", 1.8),
            ("throne", 1.2),
            ("kingdom", 1.0),
            ("hero", 1.0),
            ("army", 1.5),
            ("sword", 1.0),
            ("dragon", 1.5),
            ("quest", 1.0),
            ("destiny", 1.0),
        ),
    ),
    (
        "calm",
        (
            ("ocean", 1.2),
            ("beach", 1.0),
            ("morning coffee", 1.0),
            ("sunrise", 1.0),
            ("garden", 0.9),
            ("meditation", 1.2),
            ("peaceful", 1.3),
            ("quiet", 0.8),
            ("park", 0.7),
            ("cottage", 0.8),
        ),
    ),
]

# Extra words appended to Freesound query after mood baseline (short).
_MOOD_STYLE_TAIL = {
    "happy": "bright upbeat positive",
    "sad": "melancholic emotional",
    "tense": "suspense thriller underscore",
    "calm": "soft gentle spacious",
    "epic": "orchestral cinematic wide",
    "neutral": "subtle documentary underscore",
}


def _scene_blob(scene: Dict[str, Any]) -> str:
    parts: List[str] = []
    loc = scene.get("location")
    if isinstance(loc, str) and loc.strip():
        parts.append(loc.strip())
    for line in scene.get("dialogue") or []:
        if not isinstance(line, dict):
            continue
        for key in ("line", "visual_cue", "emotion"):
            v = line.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
    return " ".join(parts)


def _gather_story_text(jobs: List[Dict[str, Any]]) -> str:
    chunks: List[str] = []
    for job in jobs:
        sc = job.get("scene") or job.get("task") or {}
        if isinstance(sc, dict):
            chunks.append(_scene_blob(sc))
    return " ".join(chunks)


def _load_manifest_user_prompt(manifest_path: Optional[str]) -> str:
    if not manifest_path or not os.path.isfile(manifest_path):
        return ""
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("user_prompt", "prompt", "story_prompt", "original_prompt"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _score_moods(blob: str) -> Dict[str, float]:
    scores = {m: 0.0 for m in MOODS}
    scores["neutral"] = 0.25
    for mood, pairs in _MOOD_KEYWORDS:
        for word, w in pairs:
            if word in blob:
                scores[mood] += w
    return scores


def _emotion_histogram(jobs: List[Dict[str, Any]]) -> Dict[str, int]:
    hist: Dict[str, int] = {}
    for job in jobs:
        sc = job.get("scene") or job.get("task") or {}
        for line in sc.get("dialogue") or []:
            if not isinstance(line, dict):
                continue
            em = line.get("emotion")
            if isinstance(em, str) and em.strip():
                k = em.strip().lower()
                hist[k] = hist.get(k, 0) + 1
    return hist


def _freesound_boost(jobs: List[Dict[str, Any]], mood: str) -> str:
    """Short location + style tail for Freesound text search."""
    loc_bits: List[str] = []
    for job in jobs:
        sc = job.get("scene") or job.get("task") or {}
        if not isinstance(sc, dict):
            continue
        loc = sc.get("location")
        if isinstance(loc, str):
            loc = re.sub(r"[^\w\s-]", " ", loc)
            loc = " ".join(loc.split())
            if len(loc) > 2:
                loc_bits.append(loc[:48])
    head = " ".join(dict.fromkeys(loc_bits))[:90].strip()
    tail = _MOOD_STYLE_TAIL.get(mood, _MOOD_STYLE_TAIL["neutral"])
    combined = f"{head} {tail}".strip() if head else tail
    return combined[:160]


def plan_bgm(
    jobs: List[Dict[str, Any]],
    *,
    user_prompt: str = "",
    manifest_path: Optional[str] = None,
) -> BgmPlan:
    """
    Returns apply_bgm, dominant mood, freesound_boost string, volume multiplier (0–1 scale on base), reason.
    """
    blob = (_gather_story_text(jobs) + " " + (user_prompt or "")).lower()
    mp = _load_manifest_user_prompt(manifest_path)
    if mp:
        blob = blob + " " + mp.lower()

    for phrase in _NO_BGM_PHRASES:
        if phrase in blob:
            return {
                "apply_bgm": False,
                "mood": "neutral",
                "freesound_boost": "",
                "volume_multiplier": 1.0,
                "reason": f"no_bgm_phrase:{phrase}",
            }

    scores = _score_moods(blob)
    emo_hist = _emotion_histogram(jobs)
    for em, count in emo_hist.items():
        if em in scores:
            scores[em] += float(count) * 0.85
        elif em in ("fear", "anxious", "angry"):
            scores["tense"] += float(count) * 0.9
        elif em in ("joy", "excited", "happy"):
            scores["happy"] += float(count) * 0.9
        elif em in ("sad", "melancholic", "somber"):
            scores["sad"] += float(count) * 0.9

    mood = max(MOODS, key=lambda m: scores[m])
    if scores[mood] < 0.55:
        mood = "neutral"

    vol = 1.0
    for q in _QUIET_SETTINGS:
        if q in blob:
            vol = min(vol, 0.62)
    if mood == "tense" and scores["tense"] > 2.5:
        vol = min(vol, 0.78)

    boost = _freesound_boost(jobs, mood)
    top = sorted(scores.items(), key=lambda x: -x[1])[:4]
    reason = f"mood={mood};" + ",".join(f"{k}={v:.2f}" for k, v in top)
    return {
        "apply_bgm": True,
        "mood": mood,
        "freesound_boost": boost,
        "volume_multiplier": vol,
        "reason": reason,
    }
