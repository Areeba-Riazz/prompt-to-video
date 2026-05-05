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

def _probe_duration(path: str) -> float:
    """Probe file duration in seconds via ffprobe."""
    import subprocess
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            os.path.abspath(path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


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
        # We removed -shortest here because looping in the node is the main fix,
        # but this provides a fallback where audio will play even if video ends.
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", os.path.abspath(video_path),
                "-i", os.path.abspath(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-map", "0:v:0",
                "-map", "1:a:0",
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

    audio_tracks = state.get("audio_tracks", [])
    audio_durations = {int(a["scene_id"]): a["duration_sec"] for a in audio_tracks}

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
        visual_cues = " ".join(visual_cues_list) or "cinematic atmosphere"
        characters = scene.get("characters", [])

        dialogue = scene.get("dialogue") or []
        primary_char = primary_speaker_from_dialogue(dialogue)
        char_image = scene_reference_portrait(scene, char_db)
        
        # Gender extraction for better query generation
        primary_gender = "person"
        if primary_char and primary_char in char_db:
            primary_gender = (char_db[primary_char].get("gender") or "person").lower()

        char_descriptions: List[str] = []
        if primary_char and primary_char in char_db:
            info = char_db[primary_char]
            char_descriptions.append(info.get("appearance", primary_char))

        for char_name in characters:
            if char_name == primary_char:
                continue
            char_info = char_db.get(char_name, {})
            char_descriptions.append(char_info.get("appearance", char_name))

        scene_prompt = (
            f"Scene location: {location}. "
            f"Characters: {', '.join(char_descriptions) or 'unknown'}. "
            f"Visual atmosphere: {visual_cues}. "
            "Cinematic shot, professional film quality."
        )

        methods_raw = os.environ.get("VIDEO_GEN_METHODS", "pexels,hf_ai").strip()
        methods = [m.strip() for m in methods_raw.split(",") if m.strip()]
        min_bytes = int(os.environ.get("VIDEO_GEN_MIN_BYTES", "8000"))

        target_dur = audio_durations.get(scene_id, 0)

        for method in methods:
            raw_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_{method}_raw.mp4")
            try:
                registry.invoke("generate_scene_video", {
                    "scene_id": scene_id,
                    "visual_cue": visual_cues,
                    "location": location,
                    "gender": primary_gender,
                    "target_duration": target_dur,
                    "character_image_path": char_image,
                    "output_path": raw_path,
                    "method": method,
                    "scene_prompt": scene_prompt,
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
    Loops video if it's shorter than the audio to prevent cutoffs.
    """
    import subprocess
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
        audio_item = audio_index.get(scene_id, {})
        audio_path = audio_item.get("audio_path")

        char_db = _char_db_by_name(state.get("character_db", []))
        scene = job.get("scene", {})
        char_image = scene_reference_portrait(scene, char_db)

        face_items = face_groups.get(scene_id, [])
        if len(face_items) > 1:
            face_items = face_items[:1]

        for face_item in face_items:
            video_path = face_item.get("video_path")
            method = face_item.get("method", "default")
            out_path = os.path.join(output_root, "final_scenes", f"scene_{scene_id}.mp4")

            if audio_path and os.path.exists(audio_path) and video_path and os.path.exists(video_path):
                # CHECK DURATIONS: Loop video if audio is longer
                a_dur = _probe_duration(audio_path)
                v_dur = _probe_duration(video_path)
                
                final_video_input = video_path
                
                if a_dur > v_dur + 0.1:
                    logger.info(f"🔄 [LipSync] Audio ({a_dur:.1fs}) > Video ({v_dur:.1fs}). Looping video...")
                    loop_path = video_path.replace(".mp4", "_looped.mp4")
                    try:
                        subprocess.run([
                            "ffmpeg", "-y",
                            "-stream_loop", "-1", # Infinite loop
                            "-i", os.path.abspath(video_path),
                            "-t", str(a_dur + 0.5), # Limit to audio duration + small buffer
                            "-c", "copy",
                            os.path.abspath(loop_path)
                        ], capture_output=True, timeout=60)
                        if os.path.exists(loop_path) and os.path.getsize(loop_path) > 1000:
                            final_video_input = loop_path
                            logger.info(f"✅ [LipSync] Video looped successfully.")
                    except Exception as e:
                        logger.error(f"Failed to loop video: {e}")

                registry.invoke("lip_sync_aligner", {
                    "video_path": final_video_input,
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


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: Compositor (Phase 3)
# ─────────────────────────────────────────────────────────────────────────────

def compositor_node(state: StudioState) -> dict:
    """
    Phase 3 final composition step:
      1. Burn subtitles into each scene individually (parallelized).
      2. Merge the subtitled scene clips into final_output.mp4.
      3. Mix mood-based BGM under the final dialogue audio.
    """
    import concurrent.futures
    registry = _get_registry()
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    scenes_dir = os.path.join(output_root, "final_scenes")
    
    # Phase 3 and final output now live in data/outputs/ (not nested in phase2/)
    base_outputs = os.path.dirname(output_root)
    phase3_dir = os.path.join(base_outputs, "phase3")
    subtitled_dir = os.path.join(phase3_dir, "subtitled_scenes")
    os.makedirs(subtitled_dir, exist_ok=True)

    logs: list = []

    # ── Read env config ──────────────────────────────────────────────────────
    transition = os.environ.get("COMPOSITOR_TRANSITION", "xfade")
    transition_s = float(os.environ.get("COMPOSITOR_TRANSITION_S", "0.5"))
    enable_bgm = os.environ.get("COMPOSITOR_BGM", "1") != "0"
    bgm_volume = float(os.environ.get("COMPOSITOR_BGM_VOLUME", "0.12"))
    enable_subs = os.environ.get("COMPOSITOR_SUBTITLES", "1") != "0"

    jobs = state.get("scene_jobs", [])
    if not jobs:
        logger.warning("[Compositor] No scene jobs found.")
        return {"final_output_path": "", "task_logs": logs}

    # ── Step 1: Subtitles (Per Scene) ────────────────────────────────────────
    scenes_to_merge_dir = scenes_dir # Default to original scenes
    
    if enable_subs:
        report_progress("phase3", "Subtitles", "running", "Burning subtitles into each scene...")
        logger.info("📝 [Compositor] Burning subtitles per-scene...")
        
        from mcp.tools.video_tools.subtitle_tool import build_subtitle_manifest

        def process_scene_subtitle(job):
            scene_id = job["scene_id"]
            scene_data = job["scene"]
            scene_tag = _safe_tag(scene_id)
            input_path = os.path.join(scenes_dir, f"scene_{scene_id}.mp4")
            output_path = os.path.join(subtitled_dir, f"scene_{scene_id}.mp4")
            
            if not os.path.exists(input_path):
                return {"scene_id": scene_id, "ok": False, "error": "Input MP4 missing"}

            # Build relative subtitles for this scene only
            sub_entries = build_subtitle_manifest(
                scenes=[scene_data],
                output_root=output_root,
                transition_duration=0, # Relative to scene start
            )
            
            if not sub_entries:
                # No subtitles, just copy original to subtitled_dir
                shutil.copy2(input_path, output_path)
                return {"scene_id": scene_id, "ok": True, "method": "copy"}

            res = registry.invoke("subtitle_tool", {
                "video_path": input_path,
                "output_path": output_path,
                "subtitles": sub_entries,
                "font_size": 18,
            })
            return {"scene_id": scene_id, **res}

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(process_scene_subtitle, job) for job in jobs]
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                if res.get("ok"):
                    logs.append({"agent": "Subtitles", "scene_id": res["scene_id"], "event": "burned"})
                else:
                    logger.warning(f"Subtitle burn failed for scene {res.get('scene_id')}: {res.get('error')}")
        
        scenes_to_merge_dir = subtitled_dir

    # ── Step 2: Composite scenes ─────────────────────────────────────────────
    report_progress("phase3", "Compositing", "running", "Merging scene clips into final movie…")
    logger.info("🎞️ [Compositor] Merging scenes...")
    
    merged_path = os.path.join(phase3_dir, "merged.mp4")
    comp_result = registry.invoke("compositor_tool", {
        "scene_dir": scenes_to_merge_dir,
        "output_path": merged_path,
        "transition": transition,
        "transition_duration": transition_s,
    })

    if not comp_result.get("ok"):
        err = comp_result.get("error", "Unknown compositor error")
        logger.error("Compositor failed: %s", err)
        logs.append({"agent": "Compositor", "event": "failed", "error": err})
        return {"final_output_path": "", "task_logs": logs}

    logs.append({
        "agent": "Compositor",
        "event": "merged",
        "clips": comp_result.get("clips_merged"),
        "transition": transition,
    })

    current_video = merged_path

    # ── Step 3: BGM ──────────────────────────────────────────────────────────
    if enable_bgm:
        report_progress("phase3", "BGM", "running", "Mixing background music…")
        logger.info("🎵 [Compositor] Mixing BGM…")

        mood = "neutral"
        if jobs:
            first_scene = jobs[0].get("scene", {})
            dialogue = first_scene.get("dialogue", [])
            if dialogue:
                mood = dialogue[0].get("emotion", "neutral") or "neutral"

        bgm_out = os.path.join(phase3_dir, "merged_bgm.mp4")
        bgm_result = registry.invoke("bgm_tool", {
            "video_path": current_video,
            "output_path": bgm_out,
            "mood": mood,
            "volume": bgm_volume,
            "loop_bgm": True,
        })

        if bgm_result.get("ok"):
            current_video = bgm_out
            logs.append({"agent": "BGM", "event": "mixed", "mood": mood})
            logger.info("✅ [Compositor] BGM mixed")

    # ── Step 4: Finalize ─────────────────────────────────────────────────────
    final_path = os.path.join(base_outputs, "final_output.mp4")
    try:
        shutil.copy2(current_video, final_path)
    except Exception as e:
        final_path = current_video

    # Write metadata
    metadata = {
        "final_output_path": final_path,
        "transition": transition,
        "bgm_enabled": enable_bgm,
        "subtitles_enabled": enable_subs,
        "clips_merged": comp_result.get("clips_merged", 0),
        "logs": logs,
    }
    meta_path = os.path.join(phase3_dir, "composition_metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    report_progress("phase3", "Compositing", "done", f"Final output ready: {os.path.basename(final_path)}")
    logger.info("🎬 [Compositor] Phase 3 complete → %s", final_path)

    return {
        "final_output_path": final_path,
        "status": "completed",
        "task_logs": logs,
    }
