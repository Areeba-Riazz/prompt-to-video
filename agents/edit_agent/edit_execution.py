"""
Phase 5 — Edit execution bridge (modular, pipeline-safe).

Keeps LangGraph Phase 2 entry state consistent with Phase 1 artifacts on disk,
expands edit-agent scopes the graph understands (e.g. character → scenes),
and avoids breaking normal runs when these helpers are not used.
"""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("EditExecution")

DEFAULT_PHASE1_DIR = os.path.join("data", "outputs", "phase1")


def phase1_dir() -> str:
    return os.environ.get("PHASE1_OUTPUT_DIR", DEFAULT_PHASE1_DIR)


def coalesce_edit_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns a shallow copy of state with character_db populated from
    `characters` when the UI only sent the Phase 1 list shape.
    """
    out: Dict[str, Any] = dict(state or {})
    db = out.get("character_db")
    if not isinstance(db, list) or not db:
        alt = out.get("characters")
        if isinstance(alt, list) and alt:
            out["character_db"] = deepcopy(alt)
    return out


def summarize_state_for_intent(state: Optional[Dict[str, Any]]) -> str:
    """Richer context for the intent LLM (character names reduce mis-scoping)."""
    s = coalesce_edit_state(state or {})
    scenes = s.get("scenes") or []
    n = len(scenes) if isinstance(scenes, list) else 0
    chars = s.get("character_db") or []
    names = [c.get("name") for c in chars if isinstance(c, dict) and c.get("name")]
    head = ", ".join(names[:16]) if names else "unknown roster"
    return f"Project with {n} scenes. Known character names: {head}."


def pitch_param_to_edge_offset_hz(pitch: Any) -> Optional[int]:
    """
    Map classifier pitch (0.5–1.5, 1.0 = neutral) to Edge-tts Hz offset.
    Lower than 1.0 → negative Hz (deeper); above 1.0 → positive (brighter).
    """
    try:
        p = float(pitch)
    except (TypeError, ValueError):
        return None
    return int(round((p - 1.0) * 55))


def _normalize_character_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def scene_ids_for_character(manifest_path: str, character_name: str) -> List[int]:
    """Scene IDs where this speaker appears in dialogue."""
    if not manifest_path or not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read manifest %s: %s", manifest_path, e)
        return []

    scenes = manifest.get("scenes", []) if isinstance(manifest, dict) else manifest
    if not isinstance(scenes, list):
        return []

    target = _normalize_character_name(character_name)
    out: List[int] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if sid is None:
            continue
        try:
            sid_int = int(sid)
        except (TypeError, ValueError):
            continue
        dial = scene.get("dialogue") or []
        if not isinstance(dial, list):
            continue
        for line in dial:
            if not isinstance(line, dict):
                continue
            spk = line.get("speaker") or line.get("character")
            if spk and _normalize_character_name(str(spk)) == target:
                out.append(sid_int)
                break
    return sorted(set(out))


def expand_post_proc_map_character_scopes(
    post_proc_map: Dict[str, Any],
    manifest_path: str,
) -> Dict[str, Any]:
    """
    LangGraph post_proc_node only understands `global` and `scene:{id}`.
    Expand `character:{name}` entries into per-scene keys.
    """
    if not post_proc_map:
        return post_proc_map

    expanded: Dict[str, Any] = {}
    for key, val in post_proc_map.items():
        if not isinstance(key, str) or not key.startswith("character:"):
            expanded[key] = val
            continue
        char_name = key.split(":", 1)[1] if ":" in key else ""
        sids = scene_ids_for_character(manifest_path, char_name)
        if not sids:
            logger.warning(
                "No scenes found for character %r; dropping post_proc key %s",
                char_name,
                key,
            )
            continue
        for sid in sids:
            sk = f"scene:{sid}"
            base = expanded.get(sk)
            if isinstance(base, dict):
                merged = {**base, **(val if isinstance(val, dict) else {})}
                expanded[sk] = merged
            else:
                expanded[sk] = deepcopy(val) if isinstance(val, dict) else val
    return expanded


def persist_character_db(characters: List[Dict[str, Any]]) -> str:
    """Writes data/outputs/phase1/character_db.json (same envelope Phase 2 reads)."""
    p1 = phase1_dir()
    os.makedirs(p1, exist_ok=True)
    path = os.path.join(p1, "character_db.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"characters": characters}, f, indent=2)
    logger.info("Persisted character_db (%d chars) → %s", len(characters), path)
    return path


def persist_scene_manifest_scenes(scenes: List[Dict[str, Any]]) -> str:
    """Writes scene_manifest.json with {scenes: [...]} (TaskGraph / Phase 2 format)."""
    p1 = phase1_dir()
    os.makedirs(p1, exist_ok=True)
    path = os.path.join(p1, "scene_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"scenes": scenes}, f, indent=2)
    logger.info("Persisted scene manifest (%d scenes) → %s", len(scenes), path)
    return path


def apply_audio_target_to_state(
    intent: Dict[str, Any], state: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool, bool]:
    """
    Mutates coalesced state for regenerative `audio` target.
    Returns (state, character_db_dirty, scene_manifest_dirty).
    """
    scope = intent.get("scope", "") or ""
    params = intent.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}

    dirty_chars = False
    dirty_scenes = False
    if scope.startswith("character:"):
        char_name = scope.split(":", 1)[-1].strip()
        logger.info("Applying audio intent to character %r", char_name)
        db = state.get("character_db")
        if not isinstance(db, list):
            return state, False, False
        for char in db:
            if not isinstance(char, dict):
                continue
            if char.get("name") != char_name:
                continue
            if "gender" in params:
                char["gender"] = params["gender"]
                dirty_chars = True
            if "voice" in params:
                char["edge_voice"] = params["voice"]
                char["tts_voice"] = params["voice"]
                dirty_chars = True
            if "edge_voice" in params:
                char["edge_voice"] = params["edge_voice"]
                dirty_chars = True
            if "speed" in params:
                char["speed"] = params["speed"]
                dirty_chars = True
            if "pitch" in params:
                off = pitch_param_to_edge_offset_hz(params.get("pitch"))
                if off is not None:
                    char["edge_pitch_offset_hz"] = off
                    dirty_chars = True
            low = str(params).lower()
            if "male" in low and "female" not in low:
                char["gender"] = "male"
                dirty_chars = True
            if "female" in low:
                char["gender"] = "female"
                dirty_chars = True
            break

    elif scope.startswith("scene:"):
        scene_id = scope.split(":", 1)[-1].strip()
        scenes = state.get("scenes")
        if isinstance(scenes, list):
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                if str(scene.get("scene_id")) != scene_id:
                    continue
                for line in scene.get("dialogue") or []:
                    if not isinstance(line, dict):
                        continue
                    if "emotion" in params:
                        line["emotion"] = params["emotion"]
                    if "tone" in params:
                        line["emotion"] = params["tone"]
                dirty_scenes = True
                break

    if (dirty_chars or dirty_scenes) and isinstance(state.get("character_db"), list):
        state["characters"] = deepcopy(state["character_db"])
    return state, dirty_chars, dirty_scenes


def apply_video_frame_to_state(intent: Dict[str, Any], state: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Merges visual cue parameters into the scoped scene's dialogue lines. Returns (state, changed)."""
    scope = intent.get("scope", "") or ""
    params = intent.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}
    scene_id = scope.split(":")[-1] if ":" in scope else ""
    scenes = state.get("scenes")
    if not isinstance(scenes, list) or not scene_id:
        return state, False
    changed = False
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if str(sid) != str(scene_id):
            continue
        dialogue = scene.get("dialogue") or []
        if not isinstance(dialogue, list):
            break
        for line in dialogue:
            if not isinstance(line, dict):
                continue
            for key, val in params.items():
                cue = (line.get("visual_cue") or "").strip()
                frag = f"{key}: {val}".strip()
                line["visual_cue"] = f"{cue}, {frag}".strip(", ") if cue else frag
                changed = True
        break
    return state, changed


def restore_phase1_disk_from_state(state: Dict[str, Any]) -> None:
    """
    After snapshot revert, align Phase 1 JSON on disk with restored state
    so the next LangGraph invoke sees consistent inputs.
    """
    db = state.get("character_db")
    if isinstance(db, list) and db:
        persist_character_db(db)
    scenes = state.get("scenes")
    if isinstance(scenes, list) and scenes:
        persist_scene_manifest_scenes(scenes)


def hydrate_final_scenes_for_post_proc(output_root: str) -> List[Dict[str, Any]]:
    """
    Build final_scenes[] from existing disk outputs so Post_proc_node can run
    under route_after_parse(..., skip_all_gen=True) without a full synth pass.
    """
    finals: List[Dict[str, Any]] = []
    final_dir = os.path.join(output_root, "final_scenes")
    audio_dir = os.path.join(output_root, "audio_tracks")
    if not os.path.isdir(final_dir):
        return finals
    for entry in os.listdir(final_dir):
        if not (entry.startswith("scene_") and entry.endswith(".mp4")):
            continue
        try:
            sid = int(entry.replace("scene_", "").replace(".mp4", ""))
        except ValueError:
            continue
        video_path = os.path.join(final_dir, entry)
        tag = f"scene_{sid:02d}"
        wav_path = os.path.join(audio_dir, f"{tag}.wav")
        audio_path = wav_path if os.path.exists(wav_path) else video_path
        finals.append(
            {
                "scene_id": sid,
                "final_video_path": video_path,
                "audio_path": audio_path,
                "method": "post_proc_hydrated",
            }
        )
    return sorted(finals, key=lambda x: int(x["scene_id"]))
