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

from shared.repo_paths import resolve_from_repo

logger = logging.getLogger("EditExecution")

DEFAULT_PHASE1_DIR = os.path.join("data", "outputs", "phase1")


def phase1_dir() -> str:
    return resolve_from_repo(os.environ.get("PHASE1_OUTPUT_DIR", DEFAULT_PHASE1_DIR))


def _speakers_from_manifest(manifest_path: str) -> List[str]:
    """Return unique speaker names from the scene manifest (for DB sync)."""
    if not manifest_path or not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    scenes = data.get("scenes", data) if isinstance(data, dict) else data
    if not isinstance(scenes, list):
        return []
    seen: List[str] = []
    for scene in scenes:
        for line in (scene.get("dialogue") or []):
            spk = (line.get("speaker") or "").strip()
            if spk and spk not in seen:
                seen.append(spk)
    return seen


def coalesce_edit_state(state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Returns a shallow copy of state with character_db populated from
    `characters` when the UI only sent the Phase 1 list shape.

    Also ensures every speaker that appears in the scene manifest has at least
    a stub entry in character_db so voice edits can find and mutate them.
    """
    out: Dict[str, Any] = dict(state or {})
    db = out.get("character_db")
    if not isinstance(db, list) or not db:
        alt = out.get("characters")
        if isinstance(alt, list) and alt:
            out["character_db"] = deepcopy(alt)

    # Sync: add stub entries for manifest speakers not yet in character_db
    db = out.get("character_db")
    if not isinstance(db, list):
        db = []
        out["character_db"] = db

    manifest_path = out.get("scene_manifest_path") or os.path.join(phase1_dir(), "scene_manifest.json")
    manifest_speakers = _speakers_from_manifest(manifest_path)
    db_names_lower = {(c.get("name") or "").strip().lower() for c in db if isinstance(c, dict)}
    for spk in manifest_speakers:
        if spk.strip().lower() not in db_names_lower:
            db.append({
                "name": spk,
                "gender": None,
                "edge_voice": None,
                "tts_voice": None,
                "kokoro_voice": None,
            })
            db_names_lower.add(spk.strip().lower())
            logger.debug("coalesce_edit_state: added stub for manifest speaker %r", spk)
    return out


def ensure_studio_state_for_compositor(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 5 EditPanel sends a partial state (no scene_jobs). Compositor needs
    scene_jobs like scene_parser_node — hydrate from manifest via get_task_graph.
    """
    out = dict(state)
    jobs = out.get("scene_jobs")
    if isinstance(jobs, list) and len(jobs) > 0:
        return out

    manifest_path = out.get("scene_manifest_path") or os.path.join(
        phase1_dir(), "scene_manifest.json"
    )
    if manifest_path and not os.path.isabs(manifest_path):
        manifest_path = resolve_from_repo(manifest_path)
    out["scene_manifest_path"] = manifest_path
    out.setdefault(
        "output_root",
        resolve_from_repo(
            os.environ.get("PHASE2_OUTPUT_DIR", os.path.join("data", "outputs", "phase2"))
        ),
    )
    if not os.path.isfile(manifest_path):
        logger.warning(
            "ensure_studio_state_for_compositor: no scene_jobs and missing manifest %s",
            manifest_path,
        )
        return out

    try:
        from mcp.tool_registry import registry

        tg = registry.invoke(
            "get_task_graph", {"manifest_path": manifest_path, "parallel": True}
        )
        tasks = tg.get("tasks", [])
        out["scene_jobs"] = [
            {"scene_id": t["scene_id"], "scene": t, "task": t} for t in tasks
        ]
        out.setdefault("scene_manifest_path", manifest_path)
        logger.info(
            "Hydrated scene_jobs for compositor (%d scenes) from %s",
            len(out["scene_jobs"]),
            manifest_path,
        )
    except Exception as exc:
        logger.warning("ensure_studio_state_for_compositor: get_task_graph failed: %s", exc)
    return out


def studio_state_for_compositor_edit(base: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge EditPanel partial state with defaults required by compositor_node / StudioState.
    """
    h = ensure_studio_state_for_compositor(base)
    mp = h.get("scene_manifest_path") or os.path.join(phase1_dir(), "scene_manifest.json")
    if mp and not os.path.isabs(mp):
        mp = resolve_from_repo(mp)
    out_root = h.get("output_root") or resolve_from_repo(
        os.environ.get("PHASE2_OUTPUT_DIR", os.path.join("data", "outputs", "phase2"))
    )
    defaults: Dict[str, Any] = {
        "scene_manifest_path": mp,
        "output_root": out_root,
        "character_db": h.get("character_db") or [],
        "scene_id_filter": h.get("scene_id_filter"),
        "skip_video": bool(h.get("skip_video", False)),
        "skip_all_gen": bool(h.get("skip_all_gen", False)),
        "post_proc_map": dict(h.get("post_proc_map") or {}),
        "scenes": list(h.get("scenes") or []),
        "task_graph": list(h.get("task_graph") or []),
        "scene_jobs": list(h.get("scene_jobs") or []),
        "audio_tracks": list(h.get("audio_tracks") or []),
        "video_tracks": list(h.get("video_tracks") or []),
        "face_swaps": list(h.get("face_swaps") or []),
        "final_scenes": list(h.get("final_scenes") or []),
        "final_output_path": str(h.get("final_output_path") or ""),
        "task_logs": list(h.get("task_logs") or []),
        "status": str(h.get("status") or "idle"),
        "errors": list(h.get("errors") or []),
        "current_agent": str(h.get("current_agent") or "Compositor"),
    }
    merged = {**defaults, **h}
    for k, v in h.items():
        if k.startswith("_edit_") or k.startswith("_compositor_"):
            merged[k] = v
    return merged


BGM_MOODS = frozenset({"happy", "sad", "tense", "calm", "epic", "neutral"})


def should_reuse_merge_for_bgm_intent(intent: Dict[str, Any]) -> bool:
    """
    True when Phase 5 can skip subtitle burn + scene merge and only remix BGM
    (or strip BGM) using existing phase3/merged.mp4.
    """
    if intent.get("target") != "video":
        return False
    intent_id = str(intent.get("intent") or "").lower()
    if intent_id == "remove_subtitles":
        return False
    params = intent.get("parameters") or {}
    if params.get("full_composite") is True:
        return False
    if params.get("remix_bgm_only") is True:
        return True
    if params.get("remix_bgm_only") is False:
        return False
    return intent_id in (
        "adjust_bgm",
        "add_bgm",
        "change_bgm",
        "replace_bgm",
        "remove_bgm",
    )


def infer_bgm_mood_from_intent(intent: Dict[str, Any], user_query: str = "") -> tuple[str, str]:
    """
    Derive (mood, freesound_boost) from classifier parameters + natural language.
    Returns mood in BGM_MOODS or "" if not inferable; boost may be empty.
    """
    params = intent.get("parameters") or {}
    mood = str(params.get("mood", "")).strip().lower()
    boost = str(params.get("bgm_style") or params.get("music_style") or "").strip()
    blob = f"{user_query} {intent.get('intent', '')} {params}".lower()
    if mood not in BGM_MOODS:
        if any(w in blob for w in ("upbeat", "uplifting", "cheerful", "joyful", "energetic", "lively")):
            mood = "happy"
        elif any(w in blob for w in ("somber", "melancholy", "sorrow", "tearful")):
            mood = "sad"
        elif any(w in blob for w in ("tense", "suspense", "thriller", "horror", "scary")):
            mood = "tense"
        elif any(w in blob for w in ("calm", "peaceful", "soft", "gentle", "meditative")):
            mood = "calm"
        elif any(w in blob for w in ("epic", "grand", "triumph", "heroic")):
            mood = "epic"
        else:
            mood = ""
    if mood == "happy" and not boost:
        boost = "bright upbeat energetic instrumental"
    return mood, boost


def summarize_state_for_intent(state: Optional[Dict[str, Any]]) -> str:
    """
    Richer context for the intent LLM.

    Always includes the manifest speakers (not just character_db) so the LLM
    can correctly resolve names like 'Comedian' even if character_db is from
    a different Phase 1 run.
    """
    s = coalesce_edit_state(state or {})
    scenes = s.get("scenes") or []
    n = len(scenes) if isinstance(scenes, list) else 0

    # Prefer manifest speakers — they reflect who is actually in the video.
    manifest_path = s.get("scene_manifest_path") or os.path.join(phase1_dir(), "scene_manifest.json")
    manifest_spk = _speakers_from_manifest(manifest_path)

    chars = s.get("character_db") or []
    db_names = [c.get("name") for c in chars if isinstance(c, dict) and c.get("name")]

    # Union — manifest speakers first so the LLM sees them prominently.
    all_names = list(dict.fromkeys(manifest_spk + db_names))
    head = ", ".join(all_names[:20]) if all_names else "unknown roster"

    # Scene count from manifest if state scenes is empty
    if n == 0:
        try:
            with open(manifest_path, encoding="utf-8") as f:
                mdata = json.load(f)
            mscenes = mdata.get("scenes", mdata) if isinstance(mdata, dict) else mdata
            n = len(mscenes) if isinstance(mscenes, list) else 0
        except Exception:
            pass

    return f"Project with {n} scenes. Speakers in the video: {head}."


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
        char_name = scope.split(":", 1)[-1].strip().lower()
        logger.info("Applying audio intent to character %r", char_name)
        db = state.get("character_db")
        if not isinstance(db, list):
            db = []
            state["character_db"] = db

        # Find the matching entry (case-insensitive).
        # If absent, create a stub so the edit can still take effect.
        target_char: Optional[Dict[str, Any]] = None
        for char in db:
            if not isinstance(char, dict):
                continue
            if (char.get("name") or "").strip().lower() == char_name:
                target_char = char
                break

        if target_char is None:
            # Try to find the canonical-cased name from the manifest
            manifest_path = state.get("scene_manifest_path") or os.path.join(phase1_dir(), "scene_manifest.json")
            canonical = char_name  # fallback
            for spk in _speakers_from_manifest(manifest_path):
                if spk.strip().lower() == char_name:
                    canonical = spk
                    break
            logger.info(
                "Character %r not in character_db — creating stub entry so edit takes effect.",
                canonical,
            )
            target_char = {
                "name": canonical,
                "gender": None,
                "edge_voice": None,
                "tts_voice": None,
                "kokoro_voice": None,
            }
            db.append(target_char)

        char = target_char
        low = str(params).lower()

        # Explicit voice fields from the classifier
        if "voice" in params:
            char["edge_voice"] = params["voice"]
            char["tts_voice"] = params["voice"]
            dirty_chars = True
        if "edge_voice" in params:
            char["edge_voice"] = params["edge_voice"]
            dirty_chars = True

        # Gender change — clear any stored voice so voice_mapping
        # picks from the correct gender pool on re-synthesis.
        new_gender: Optional[str] = None
        if "gender" in params:
            new_gender = params["gender"]
        elif "male" in low and "female" not in low:
            new_gender = "male"
        elif "female" in low:
            new_gender = "female"

        if new_gender:
            char["gender"] = new_gender
            dirty_chars = True
            # Only wipe stored voice fields if the caller didn't
            # supply an explicit replacement voice in this same call.
            if "voice" not in params and "edge_voice" not in params:
                char["edge_voice"] = None
                char["tts_voice"] = None
                char["kokoro_voice"] = None
                logger.info(
                    "Cleared stored voice for %r; new gender=%r — "
                    "voice_mapping will assign a %s voice on re-synthesis.",
                    char.get("name"), new_gender, new_gender,
                )

        if "speed" in params:
            char["speed"] = params["speed"]
            dirty_chars = True
        if "pitch" in params:
            off = pitch_param_to_edge_offset_hz(params.get("pitch"))
            if off is not None:
                char["edge_pitch_offset_hz"] = off
                dirty_chars = True

        logger.info(
            "Audio intent applied to %r: gender=%r edge_voice=%r dirty=%s",
            char.get("name"), char.get("gender"), char.get("edge_voice"), dirty_chars,
        )

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
