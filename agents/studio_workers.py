"""
Studio Workers — agents/studio_workers.py
Phase 2 worker functions. Each one queries the MCP registry at runtime
(no direct model imports). This satisfies the 'no hardcoding' MCP contract.
"""

import json
import os
from typing import Any, Dict, List, Optional

from schema.phase2_state import StudioState


def _get_registry():
    """Lazily return the Phase 2 MCP registry singleton."""
    from tools.mcp_registry import registry
    return registry


def _char_db_by_name(character_db_list: List[Dict]) -> Dict[str, Dict]:
    """Convert character_db list to a dict keyed by character name."""
    return {c["name"]: c for c in character_db_list}


def _safe_tag(scene_id: int) -> str:
    return f"scene_{int(scene_id):02d}"


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Scene Parser
# ─────────────────────────────────────────────────────────────────────────────

def scene_parser_node(state: StudioState) -> dict:
    """
    Reads scene_manifest.json via MCP get_task_graph tool.
    Produces structured scene_jobs list consumed by all downstream workers.
    """
    registry = _get_registry()
    manifest_path = state.get("scene_manifest_path", "output/scene_manifest.json")
    output_root = state.get("output_root", "output_phase2")

    if not os.path.exists(manifest_path):
        return {
            "status": "failed",
            "errors": [f"Missing scene manifest: {manifest_path}"],
            "current_agent": "SceneParser",
        }

    task_graph_result = registry.invoke("get_task_graph", {
        "manifest_path": manifest_path,
        "parallel": True,
    })

    tasks = task_graph_result.get("tasks", [])

    # Build scene_jobs — these are the atomic units passed to downstream nodes
    scene_jobs = []
    scene_id_filter = state.get("scene_id_filter")

    for task in tasks:
        if scene_id_filter is not None and int(task["scene_id"]) != scene_id_filter:
            continue
        scene_jobs.append({
            "scene_id": task["scene_id"],
            "scene": task,   # full task dict (has dialogue, visual_cues, etc.)
            "task": task,
        })

    return {
        "scenes": tasks,
        "task_graph": tasks,
        "scene_jobs": scene_jobs,
        "status": "processing",
        "current_agent": "SceneParser",
        "task_logs": [{
            "agent": "SceneParser",
            "event": "task_graph_created",
            "total_scenes": len(tasks),
            "parallel_enabled": task_graph_result.get("parallel_enabled", True),
        }],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Voice Synthesis
# ─────────────────────────────────────────────────────────────────────────────

def voice_synth_node(state: StudioState) -> dict:
    """
    Synthesizes per-scene audio via MCP voice_cloning_synthesizer tool.
    Concatenates all dialogue lines per scene with 0.3 s silence between.
    """
    registry = _get_registry()
    output_root = state.get("output_root", "output_phase2")
    jobs = state.get("scene_jobs", [])
    character_db_list = state.get("character_db", [])
    char_db = _char_db_by_name(character_db_list) if character_db_list else {}

    audio_tracks: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    for job in jobs:
        scene = job.get("scene", {})
        scene_id = int(job["scene_id"])
        scene_tag = _safe_tag(scene_id)
        dialogue_lines = scene.get("dialogue", [])

        # --- synthesize each line individually, then concatenate ---
        import wave
        import struct
        import math
        import shutil

        segment_paths: List[str] = []
        temp_dir = os.path.join(output_root, "temp_audio", scene_tag)
        os.makedirs(temp_dir, exist_ok=True)

        for i, line in enumerate(dialogue_lines):
            speaker = line.get("speaker", "A")
            text = line.get("line", "")
            emotion = line.get("emotion", "neutral")
            char_info = char_db.get(speaker, {})
            ref_audio = char_info.get("reference_audio", None)

            line_path = os.path.join(temp_dir, f"line_{i:02d}.wav")
            try:
                registry.invoke("voice_cloning_synthesizer", {
                    "character_name": speaker,
                    "dialogue": text,
                    "output_path": line_path,
                    "reference_audio_path": ref_audio,
                    "emotion": emotion,
                })
                if os.path.exists(line_path):
                    segment_paths.append(line_path)
            except Exception as e:
                print(f"[VoiceNode] Line {i} scene {scene_id} failed: {e}")

        # Concatenate segments
        combined_path = os.path.join(output_root, "audio_tracks", f"{scene_tag}.wav")
        os.makedirs(os.path.dirname(combined_path), exist_ok=True)

        if segment_paths:
            _concat_wavs(segment_paths, combined_path)
        else:
            # Fallback: single synthesized full-scene text
            full_text = " ".join(
                f"{dl.get('speaker','')}: {dl.get('line','')}" for dl in dialogue_lines
            ) or "Ambient silence."
            registry.invoke("voice_cloning_synthesizer", {
                "character_name": "A",
                "dialogue": full_text,
                "output_path": combined_path,
                "reference_audio_path": None,
                "emotion": "neutral",
            })

        duration = _wav_duration(combined_path)
        audio_tracks.append({
            "scene_id": scene_id,
            "audio_path": combined_path,
            "duration_sec": duration,
        })
        logs.append({
            "agent": "VoiceSynth",
            "scene_id": scene_id,
            "audio_path": combined_path,
            "segments": len(segment_paths),
        })

    return {"audio_tracks": audio_tracks, "task_logs": logs}


def _concat_wavs(paths: List[str], out_path: str) -> None:
    """
    Concatenate WAV/audio files into a single WAV.
    Tries: ffmpeg concat → soundfile/numpy → stdlib copy.
    """
    import subprocess
    import tempfile

    valid_paths = [p for p in paths if os.path.exists(p)]
    if not valid_paths:
        return

    # Method 1: ffmpeg concat filter (works with WAV from edge-tts)
    try:
        # Build ffmpeg concat command with silence padding between segments
        inputs = []
        filter_parts = []
        for i, p in enumerate(valid_paths):
            inputs += ["-i", p]
            # Each segment + 0.3s silence
            filter_parts.append(f"[{i}:a]apad=pad_dur=0.3[a{i}]")
        concat_inputs = "".join(f"[a{i}]" for i in range(len(valid_paths)))
        filter_complex = ";".join(filter_parts) + f";{concat_inputs}concat=n={len(valid_paths)}:v=0:a=1[out]"
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-ar", "16000", "-ac", "1",
            out_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return
    except Exception:
        pass

    # Method 2: soundfile + numpy
    try:
        import soundfile as sf  # type: ignore
        import numpy as np

        segments = []
        sr = None
        for p in valid_paths:
            data, file_sr = sf.read(p)
            if sr is None:
                sr = file_sr
            segments.append(data)
            segments.append(np.zeros(int(0.3 * file_sr)))

        if segments and sr:
            sf.write(out_path, np.concatenate(segments), sr)
            return
    except Exception:
        pass

    # Method 3: copy first valid segment
    import shutil
    shutil.copy2(valid_paths[0], out_path)


def _mux_audio_video(video_path: str, audio_path: str, output_path: str) -> bool:
    """
    Mux an audio track into a video file using ffmpeg.
    Always produces a video+audio MP4 regardless of what the lip sync engine did.
    Returns True on success.
    """
    import subprocess
    import shutil

    if not audio_path or not os.path.exists(audio_path):
        return False
    if not video_path or not os.path.exists(video_path):
        return False

    tmp = output_path + "._mux_tmp.mp4"
    try:
        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", os.path.abspath(video_path),
            "-i", os.path.abspath(audio_path),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            os.path.abspath(tmp),
        ], capture_output=True, timeout=120)

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


def _wav_duration(path: str) -> float:
    """Return duration of a WAV file in seconds."""
    try:
        import wave
        with wave.open(path, "r") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: Video Generation
# ─────────────────────────────────────────────────────────────────────────────

def video_gen_node(state: StudioState) -> dict:
    """
    Generates raw scene videos via MCP generate_scene_video tool.
    Uses character portraits from Phase 1 as anchor images.
    """
    registry = _get_registry()
    output_root = state.get("output_root", "output_phase2")
    jobs = state.get("scene_jobs", [])
    character_db_list = state.get("character_db", [])
    char_db = _char_db_by_name(character_db_list) if character_db_list else {}

    video_tracks: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    os.makedirs(os.path.join(output_root, "raw_scenes"), exist_ok=True)

    task_graph = state.get("task_graph", [])

    for job in jobs:
        scene = job.get("scene", {})
        scene_id = int(job["scene_id"])
        scene_tag = _safe_tag(scene_id)

        location = scene.get("location", "")
        
        # Extract visual cues from the dialogue array
        visual_cues_list = []
        for d in scene.get("dialogue", []):
            if "visual_cue" in d:
                visual_cues_list.append(d["visual_cue"])
        visual_cues = " ".join(visual_cues_list) if visual_cues_list else ""
        
        characters = scene.get("characters", [])

        # Find primary speaker for this scene (character with most dialogue lines)
        speaker_counts: Dict[str, int] = {}
        for task in task_graph:
            if int(task.get("scene_id", -1)) == scene_id:
                for line in task.get("lines", []):
                    spk = line.get("speaker", "").strip()
                    if spk:
                        speaker_counts[spk] = speaker_counts.get(spk, 0) + 1
        primary_char = max(speaker_counts, key=speaker_counts.get) if speaker_counts else ""

        # Build enriched scene prompt
        char_descriptions = []
        char_image: Optional[str] = None

        # Try primary speaker portrait first
        if primary_char and primary_char in char_db:
            info = char_db[primary_char]
            char_descriptions.append(info.get("appearance", primary_char))
            candidate = info.get("image_path", "")
            if candidate and os.path.exists(candidate):
                char_image = candidate

        # Collect other character descriptions and fallback portraits
        for char_name in characters:
            if char_name == primary_char:
                continue
            char_info = char_db.get(char_name, {})
            char_descriptions.append(char_info.get("appearance", char_name))
            if char_image is None:
                candidate = char_info.get("image_path", "")
                if candidate and os.path.exists(candidate):
                    char_image = candidate

        print(f"[VideoGen] Scene {scene_id} primary speaker: {primary_char or 'unknown'} — portrait: {os.path.basename(char_image) if char_image else 'none'}")

        scene_prompt = (
            f"Scene location: {location}. "
            f"Characters: {', '.join(char_descriptions) or 'unknown'}. "
            f"Visual atmosphere: {visual_cues}. "
            "Cinematic shot, professional film quality."
        )

        methods_to_run = ["pexels", "hf_ai"]
        for method in methods_to_run:
            raw_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_{method}_raw.mp4")
            try:
                registry.invoke("generate_scene_video", {
                    "scene_id": scene_id,
                    "scene_prompt": scene_prompt,
                    "character_image_path": char_image,
                    "output_path": raw_path,
                    "characters": characters,
                    "method": method
                })
                video_tracks.append({
                    "scene_id": scene_id,
                    "video_path": raw_path,
                    "character_image": char_image,
                    "method": method
                })
                logs.append({
                    "agent": "VideoGen",
                    "scene_id": scene_id,
                    "method": method,
                    "video_path": raw_path,
                })
            except Exception as e:
                print(f"[VideoGen] Error generating scene {scene_id} ({method}): {e}")

    return {"video_tracks": video_tracks, "task_logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: Face Swap
# ─────────────────────────────────────────────────────────────────────────────

def face_swap_node(state: StudioState) -> dict:
    """
    Applies identity-aware face mapping via MCP face_swapper tool.
    Validates identity first via MCP identity_validator tool.
    Falls back gracefully if InsightFace is unavailable.
    """
    registry = _get_registry()
    output_root = state.get("output_root", "output_phase2")
    jobs = state.get("scene_jobs", [])
    video_groups = {}
    for v in state.get("video_tracks", []):
        video_groups.setdefault(int(v["scene_id"]), []).append(v)
        
    character_db_list = state.get("character_db", [])
    char_db = _char_db_by_name(character_db_list) if character_db_list else {}

    face_swaps: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    for job in jobs:
        scene = job.get("scene", {})
        scene_id = int(job["scene_id"])
        scene_tag = _safe_tag(scene_id)
        characters = scene.get("characters", [])

        # Process each video branch for this scene
        for video_item in video_groups.get(scene_id, []):
            src_path = video_item.get("video_path")
            method = video_item.get("method", "default")
            
            if not src_path or not os.path.exists(src_path):
                logs.append({"agent": "FaceSwap", "scene_id": scene_id, "method": method, "event": "skipped_no_video"})
                face_swaps.append({"scene_id": scene_id, "video_path": src_path or "", "method": method})
                continue

            # Pick primary character's portrait
            char_image: Optional[str] = None
            for char_name in characters:
                candidate = char_db.get(char_name, {}).get("image_path")
                if candidate and os.path.exists(candidate):
                    char_image = candidate
                    break

            out_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_{method}_swapped.mp4")

            if char_image:
                # Validate identity first (MCP contract)
                is_valid = registry.invoke("identity_validator", {"image_path": char_image})
                if is_valid:
                    try:
                        registry.invoke("face_swapper", {
                            "source_face_image": char_image,
                            "target_video": src_path,
                            "output_path": out_path,
                        })
                        face_swaps.append({"scene_id": scene_id, "video_path": out_path, "method": method})
                        logs.append({"agent": "FaceSwap", "scene_id": scene_id, "method": method, "video_path": out_path})
                        continue
                    except Exception as e:
                        print(f"[FaceSwap] Error rendering {method}: {e}")

            # No valid portrait or failed — copy video through
            import shutil
            shutil.copy2(src_path, out_path)
            face_swaps.append({"scene_id": scene_id, "video_path": out_path, "method": method})
            logs.append({
                "agent": "FaceSwap", "scene_id": scene_id, "method": method,
                "event": "passthrough_no_face", "video_path": out_path,
            })

    return {"face_swaps": face_swaps, "task_logs": logs}


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: Lip Sync
# ─────────────────────────────────────────────────────────────────────────────

def lip_sync_node(state: StudioState) -> dict:
    """
    Fuses audio + face-swapped video via MCP lip_sync_aligner tool.
    Writes the final task log to disk.
    """
    registry = _get_registry()
    output_root = state.get("output_root", "output_phase2")
    jobs = state.get("scene_jobs", [])
    audio_index = {int(a["scene_id"]): a for a in state.get("audio_tracks", [])}
    
    face_groups = {}
    for f in state.get("face_swaps", []):
        face_groups.setdefault(int(f["scene_id"]), []).append(f)

    finals: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    os.makedirs(os.path.join(output_root, "raw_scenes"), exist_ok=True)

    for job in jobs:
        scene_id = int(job["scene_id"])
        scene_tag = _safe_tag(scene_id)
        audio_item = audio_index.get(scene_id, {})
        audio_path = audio_item.get("audio_path")
        
        for face_item in face_groups.get(scene_id, []):
            video_path = face_item.get("video_path")
            method = face_item.get("method", "default")

            out_path = os.path.join(output_root, "raw_scenes", f"{scene_tag}_{method}_final.mp4")

            char_image: Optional[str] = None
            characters = job.get("scene", {}).get("characters", [])
            char_db = _char_db_by_name(state.get("character_db", []))
            for char_name in characters:
                candidate = char_db.get(char_name, {}).get("image_path")
                if candidate and os.path.exists(candidate):
                    char_image = candidate
                    break

            if audio_path and os.path.exists(audio_path) and video_path and os.path.exists(video_path):
                registry.invoke("lip_sync_aligner", {
                    "video_path": video_path,
                    "audio_path": audio_path,
                    "output_path": out_path,
                    "source_image": char_image,
                })
            else:
                import shutil
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
                "method": method
            })
            logs.append({"agent": "LipSync", "scene_id": scene_id, "method": method, "video_path": out_path})

    # Write cumulative task log
    all_logs = state.get("task_logs", []) + logs
    log_path = os.path.join(output_root, "task_logs", "phase2_task_log.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

    logs.append({
        "agent": "LipSync",
        "event": "task_log_written",
        "path": log_path,
    })

    return {
        "final_scenes": finals,
        "task_logs": logs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 6: Memory Commit (ChromaDB)
# ─────────────────────────────────────────────────────────────────────────────

def memory_commit_node(state: StudioState) -> dict:
    """
    Stores scene metadata and final outputs to ChromaDB for pipeline resumability.
    """
    import chromadb
    
    logs = []
    output_root = state.get("output_root", "output_phase2")
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
            
            final_vid = ""
            for f in finals:
                if f["scene_id"] == scene_id:
                    final_vid = f.get("final_video_path", "")
                    
            if not final_vid:
                continue
                
            collection.add(
                documents=[json.dumps(scene_data)],
                metadatas=[{"scene_id": scene_id, "video_path": final_vid}],
                ids=[scene_tag]
            )
            
        logs.append({"agent": "MemoryCommit", "event": "chromadb_saved", "db_path": db_path})
        print(f"[MemoryCommit] Successfully saved {len(finals)} scenes to ChromaDB at {db_path}")
    except Exception as e:
        print(f"[MemoryCommit] Failed to commit to ChromaDB: {e}")
        logs.append({"agent": "MemoryCommit", "event": "chromadb_failed", "error": str(e)})

    return {
        "status": "completed",
        "task_logs": logs,
    }
