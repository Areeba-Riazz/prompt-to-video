"""
Modular TTS voice selection (Edge / Kokoro).

Character DB optional fields:
  gender: male | female | neutral (aliases: m/f, man/woman, …)
  edge_voice: explicit Edge neural voice id, e.g. en-US-JennyNeural
  tts_voice: alias for edge_voice (Edge path); Kokoro uses kokoro_voice if added later
"""

from __future__ import annotations

import hashlib
from typing import Optional

# Edge — gender pools (stable assignment via hash within pool)
_EDGE_MALE = [
    "en-US-GuyNeural",
    "en-US-DavisNeural",
    "en-GB-RyanNeural",
    "en-AU-WilliamNeural",
    "en-IN-PrabhatNeural",
]
_EDGE_FEMALE = [
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-US-JaneNeural",
    "en-GB-SoniaNeural",
    "en-AU-NatashaNeural",
    "en-CA-ClaraNeural",
    "en-IN-NeerjaNeural",
]
_EDGE_ANY = _EDGE_MALE + _EDGE_FEMALE

_LEGACY_EDGE = {
    "Kael": "en-US-GuyNeural",
    "Sora": "en-US-JennyNeural",
    "Warden AI": "en-GB-RyanNeural",
    "A": "en-US-GuyNeural",
    "B": "en-US-JennyNeural",
    "C": "en-GB-RyanNeural",
    "D": "en-AU-WilliamNeural",
}

_KOKORO_MALE = ["am_adam", "am_michael", "bm_george"]
_KOKORO_FEMALE = ["af_sarah", "af_bella", "bf_emma"]
_KOKORO_ANY = _KOKORO_MALE + _KOKORO_FEMALE

_LEGACY_KOKORO = {
    "Kael": "am_adam",
    "Sora": "af_sarah",
    "Warden AI": "bf_emma",
    "A": "am_adam",
    "B": "af_sarah",
    "C": "bf_emma",
    "D": "bm_george",
}


def _norm_gender(gender: Optional[str]) -> Optional[str]:
    if gender is None:
        return None
    x = str(gender).strip().lower()
    if x in ("m", "male", "man", "boy", "he"):
        return "male"
    if x in ("f", "female", "woman", "girl", "she"):
        return "female"
    if x in ("nb", "nonbinary", "non-binary", "neutral", "other", "they"):
        return "neutral"
    return None


def edge_voice_for_character(
    character_name: str,
    *,
    gender: Optional[str] = None,
    edge_voice: Optional[str] = None,
) -> str:
    explicit = (edge_voice or "").strip()
    if explicit:
        return explicit
    name = (character_name or "Narrator").strip() or "Narrator"
    if name in _LEGACY_EDGE:
        return _LEGACY_EDGE[name]
    g = _norm_gender(gender)
    pool = _EDGE_FEMALE if g == "female" else _EDGE_MALE if g == "male" else _EDGE_ANY
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


def kokoro_voice_for_character(
    character_name: str,
    *,
    gender: Optional[str] = None,
    kokoro_voice: Optional[str] = None,
) -> str:
    explicit = (kokoro_voice or "").strip()
    if explicit:
        return explicit
    name = (character_name or "Narrator").strip() or "Narrator"
    if name in _LEGACY_KOKORO:
        return _LEGACY_KOKORO[name]
    g = _norm_gender(gender)
    pool = _KOKORO_FEMALE if g == "female" else _KOKORO_MALE if g == "male" else _KOKORO_ANY
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]
