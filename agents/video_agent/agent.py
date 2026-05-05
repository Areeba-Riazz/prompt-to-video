"""
Video Agent — agent.py
Contains video generation, face swap, lip sync, and memory commit logic
extracted from agents/studio_workers.py.

LangGraph node functions exported:
    video_gen_node(state)      -> dict
    face_swap_node(state)      -> dict
    lip_sync_node(state)       -> dict
    memory_commit_node(state)  -> dict
"""

import json
import os
import shutil
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("VideoAgent")
from shared.utils.progress import report_progress

from shared.schemas.phase2_state import StudioState
from shared.utils.phase2_scene_helpers import scene_reference_portrait
from shared.utils.scene_dialogue import primary_speaker_from_dialogue


def _get_registry():
    """Lazily return the Phase 2 MCP registry singleton."""
    from mcp.tool_registry import registry
    return registry


def _char_db_by_name(character_db_list: List[Dict]) -> Dict[str, Dict]:
    return {c["name"]: c for c in character_db_list}


def _safe_tag(scene_id: int) -> str:
    return f"scene_{int(scene_id):02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Audio/video mux helper
# ─────────────────────────────────────────────────────────────────────────────

def _mux_audio_video(video_path: str, audio_path: str, output_path: str) -> bool:
    """
    Mux an audio track into a video file using ffmpeg.
    Returns True on success.
    """
    import subprocess

    if not audio_path or not os.path.exists(audio_path):
        return False
    if not video_path or not os.path.exists(video_path):
        return False

    tmp = output_path + "._mux_tmp.mp4"
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", os.path.abspath(video_path),
                "-i", os.path.abspath(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                os.path.abspath(tmp),
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 1000:
            shutil.move(tmp, output_path)
            print(f"[AudioMux] Audio muxed into {os.path.basename(output_path)}")
            return True
        else:
            err = (result.stderr or b"").decode(errors="ignore")[-300:]
            print(f"[AudioMux] ffmpeg mux failed: {err}")
    except Exception as e:
        print(f"[AudioMux] Exception: {e}")
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Video Generation
# ─────────────────────────────────────────────────────────────────────────────

def video_gen_node(state: StudioState) -> dict:
    """
    Generates raw scene videos via MCP generate_scene_video tool.
    Uses character portraits from Phase 1 as anchor images.
    """
    registry = _get_registry()
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    jobs = state.get("scene_jobs", [])
    character_db_list = state.get("character_db", [])
    char_db = _char_db_by_name(character_db_list) if character_db_list else {}

    video_tracks: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    os.makedirs(os.path.join(output_root, "raw_scenes"), exist_ok=True)

    for job in jobs:
        scene = job.get("scene", {})
        scene_id = int(job["scene_id"])
        report_progress("phase2", "Video Gen", "running", f"Generating video footage for Scene {scene_id}...")
        logger.info(f"🎬 [VideoGen] Generating raw footage for Scene {scene_id}...")
        scene_tag = _safe_tag(scene_id)

        location = scene.get("location", "")
        visual_cues_list = [
            d["visual_cue"] for d in scene.get("dialogue", []) if "visual_cue" in d
        ]
        visual_cues = " ".join(visual_cues_list)
        characters = scene.get("characters", [])

        dialogue = scene.get("dialogue") or []
        primary_char = primary_speaker_from_dialogue(dialogue)
        char_image = scene_reference_portrait(scene, char_db)

        char_descriptions: List[str] = []
        if primary_char and primary_char in char_db:
            info = char_db[primary_char]
            char_descriptions.append(info.get("appearance", primary_char))

        for char_name in characters:
            if char_name == primary_char:
                continue
            char_info = char_db.get(char_name, {})
            char_descriptions.append(char_info.get("appearance", char_name))

        logger.info(
            f"   -> Primary speaker: {primary_char or 'unknown'} "
            f"— portrait: {os.path.basename(char_image) if char_image else 'none'}"
        )

        scene_prompt = (
            f"Scene location: {location}. "
            f"Characters: {', '.join(char_descriptions) or 'unknown'}. "
            f"Visual atmosphere: {visual_cues}. "
            "Cinematic shot, professional film quality."
        )

        # One clip per scene — previously we ran pexels AND hf_ai, which duplicated lip-sync work,
        # overwrote the same final_scenes/scene_N.mp4 twice, and could replace good stock with a black HF fallback.
        methods_raw = os.environ.get("VIDEO_GEN_METHODS", "pexels,hf_ai").strip()
        methods = [m.strip() for m in methods_raw.split(",") if m.strip()]
        min_bytes = int(os.environ.get("VIDEO_GEN_MIN_BYTES", "8000"))

        for method in methods:
            raw_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_{method}_raw.mp4")
            try:
                registry.invoke("generate_scene_video", {
                    "scene_id": scene_id,
                    "scene_prompt": scene_prompt,
                    "character_image_path": char_image,
                    "output_path": raw_path,
                    "characters": characters,
                    "method": method,
                })
                ok = os.path.exists(raw_path) and os.path.getsize(raw_path) >= min_bytes
                if ok:
                    video_tracks.append({
                        "scene_id": scene_id,
                        "video_path": raw_path,
                        "character_image": char_image,
                        "method": method,
                    })
                    logs.append({
                        "agent": "VideoGen",
                        "scene_id": scene_id,
                        "method": method,
                        "video_path": raw_path,
                    })
                    break
                logger.warning(
                    "VideoGen scene %s method %s produced missing/tiny file (%s); trying next method.",
                    scene_id,
                    method,
                    raw_path,
                )
            except Exception as e:
                print(f"[VideoGen] Error generating scene {scene_id} ({method}): {e}")

        if not any(int(v["scene_id"]) == scene_id for v in video_tracks):
            logger.warning(
                "VideoGen scene %s: no successful API clip — invoking fallback path (portrait still / slate).",
                scene_id,
            )
            raw_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_fallback_raw.mp4")
            try:
                registry.invoke("generate_scene_video", {
                    "scene_id": scene_id,
                    "scene_prompt": scene_prompt,
                    "character_image_path": char_image,
                    "output_path": raw_path,
                    "characters": characters,
                    "method": "pexels",
                })
                if os.path.exists(raw_path) and os.path.getsize(raw_path) >= min_bytes:
                    video_tracks.append({
                        "scene_id": scene_id,
                        "video_path": raw_path,
                        "character_image": char_image,
                        "method": "fallback",
                    })
                    logs.append({
                        "agent": "VideoGen",
                        "scene_id": scene_id,
                        "method": "fallback",
                        "video_path": raw_path,
                    })
            except Exception as e:
                logger.error("VideoGen scene %s fallback invoke failed: %s", scene_id, e)

    return {"video_tracks": video_tracks, "task_logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Face Swap
# ─────────────────────────────────────────────────────────────────────────────

def face_swap_node(state: StudioState) -> dict:
    """
    Applies identity-aware face mapping via MCP face_swapper tool.
    Portrait paths are resolved from character_db; primary speaker is preferred.
    Identity validation is advisory — swap is still attempted when a portrait path exists.
    Falls back gracefully if InsightFace is unavailable.
    """
    registry = _get_registry()
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    jobs = state.get("scene_jobs", [])

    video_groups: Dict[int, List] = {}
    for v in state.get("video_tracks", []):
        video_groups.setdefault(int(v["scene_id"]), []).append(v)

    character_db_list = state.get("character_db", [])
    char_db = _char_db_by_name(character_db_list) if character_db_list else {}

    face_swaps: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    for job in jobs:
        scene = job.get("scene", {})
        scene_id = int(job["scene_id"])
        report_progress("phase2", "Face Swap", "running", f"Swapping faces for Scene {scene_id}...")
        logger.info(f"👤 [FaceSwap] Mapping identity for Scene {scene_id}...")
        scene_tag = _safe_tag(scene_id)

        for video_item in video_groups.get(scene_id, []):
            src_path = video_item.get("video_path")
            method = video_item.get("method", "default")

            if not src_path or not os.path.exists(src_path):
                logs.append({
                    "agent": "FaceSwap", "scene_id": scene_id,
                    "method": method, "event": "skipped_no_video",
                })
                face_swaps.append({"scene_id": scene_id, "video_path": src_path or "", "method": method})
                continue

            char_image = scene_reference_portrait(scene, char_db)

            out_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_{method}_swapped.mp4")

            if char_image:
                is_valid = registry.invoke("identity_validator", {"image_path": char_image})
                if not is_valid:
                    logger.warning(
                        "FaceSwap scene %s: portrait validation weak (%s) — attempting swap anyway.",
                        scene_id,
                        os.path.basename(char_image),
                    )
                try:
                    registry.invoke("face_swapper", {
                        "source_face_image": char_image,
                        "target_video": src_path,
                        "output_path": out_path,
                    })
                    face_swaps.append({"scene_id": scene_id, "video_path": out_path, "method": method})
                    logs.append({
                        "agent": "FaceSwap", "scene_id": scene_id,
                        "method": method, "video_path": out_path,
                    })
                    continue
                except Exception as e:
                    print(f"[FaceSwap] Error rendering {method}: {e}")

            shutil.copy2(src_path, out_path)
            face_swaps.append({"scene_id": scene_id, "video_path": out_path, "method": method})
            logs.append({
                "agent": "FaceSwap", "scene_id": scene_id, "method": method,
                "event": "passthrough_no_face", "video_path": out_path,
            })

    return {"face_swaps": face_swaps, "task_logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: Lip Sync
# ─────────────────────────────────────────────────────────────────────────────

def lip_sync_node(state: StudioState) -> dict:
    """
    Fuses audio + face-swapped video via MCP lip_sync_aligner tool.
    Writes the final task log to disk.
    """
    registry = _get_registry()
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    jobs = state.get("scene_jobs", [])
    audio_index = {int(a["scene_id"]): a for a in state.get("audio_tracks", [])}

    face_groups: Dict[int, List] = {}
    for f in state.get("face_swaps", []):
        face_groups.setdefault(int(f["scene_id"]), []).append(f)

    finals: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    os.makedirs(os.path.join(output_root, "raw_scenes"), exist_ok=True)
    os.makedirs(os.path.join(output_root, "final_scenes"), exist_ok=True)

    for job in jobs:
        scene_id = int(job["scene_id"])
        report_progress("phase2", "Lip Sync", "running", f"Aligning lip sync for Scene {scene_id}...")
        logger.info(f"🔊 [LipSync] Aligning dialogue for Scene {scene_id}...")
        scene_tag = _safe_tag(scene_id)
        audio_item = audio_index.get(scene_id, {})
        audio_path = audio_item.get("audio_path")

        char_db = _char_db_by_name(state.get("character_db", []))
        scene = job.get("scene", {})
        char_image = scene_reference_portrait(scene, char_db)

        face_items = face_groups.get(scene_id, [])
        if len(face_items) > 1:
            logger.warning(
                "LipSync scene %s: %d video candidates — processing first only (same output path otherwise).",
                scene_id,
                len(face_items),
            )
            face_items = face_items[:1]

        for face_item in face_items:
            video_path = face_item.get("video_path")
            method = face_item.get("method", "default")
            # Final output goes to centralized folder
            out_path = os.path.join(output_root, "final_scenes", f"scene_{scene_id}.mp4")

            if audio_path and os.path.exists(audio_path) and video_path and os.path.exists(video_path):
                registry.invoke("lip_sync_aligner", {
                    "video_path": video_path,
                    "audio_path": audio_path,
                    "output_path": out_path,
                    "source_image": char_image,
                })
            else:
                src = video_path or ""
                if src and os.path.exists(src):
                    shutil.copy2(src, out_path)
                logs.append({
                    "agent": "LipSync", "scene_id": scene_id, "method": method,
                    "event": "skipped_missing_prerequisites",
                })

            finals.append({
                "scene_id": scene_id,
                "final_video_path": out_path,
                "audio_path": audio_path,
                "method": method,
            })
            logs.append({
                "agent": "LipSync", "scene_id": scene_id,
                "method": method, "video_path": out_path,
            })

    # Write cumulative task log
    all_logs = state.get("task_logs", []) + logs
    log_path = os.path.join(output_root, "task_logs", "phase2_task_log.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

    logs.append({"agent": "LipSync", "event": "task_log_written", "path": log_path})
    return {"final_scenes": finals, "task_logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: Memory Commit
# ─────────────────────────────────────────────────────────────────────────────

def memory_commit_node(state: StudioState) -> dict:
    """
    Stores scene metadata and final outputs to ChromaDB for pipeline resumability.
    """
    logger.info("💾 [MemoryCommit] Finalizing Phase 2 records...")
    import chromadb

    logs = []
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    db_path = os.path.join(output_root, "memory_db")
    os.makedirs(db_path, exist_ok=True)

    try:
        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_or_create_collection(name="studio_memory")

        finals = state.get("final_scenes", [])
        jobs = state.get("scene_jobs", [])

        for job in jobs:
            scene_id = job["scene_id"]
            scene_data = job["scene"]
            scene_tag = _safe_tag(scene_id)

            final_vid = next(
                (f.get("final_video_path", "") for f in finals if f["scene_id"] == scene_id),
                "",
            )
            if not final_vid:
                continue

            collection.add(
                documents=[json.dumps(scene_data)],
                metadatas=[{"scene_id": scene_id, "video_path": final_vid}],
                ids=[scene_tag],
            )

        logs.append({"agent": "MemoryCommit", "event": "chromadb_saved", "db_path": db_path})
        print(f"[MemoryCommit] Successfully saved {len(finals)} scenes to ChromaDB at {db_path}")
    except Exception as e:
        print(f"[MemoryCommit] Failed to commit to ChromaDB: {e}")
        logs.append({"agent": "MemoryCommit", "event": "chromadb_failed", "error": str(e)})

    return {"status": "completed", "task_logs": logs}
