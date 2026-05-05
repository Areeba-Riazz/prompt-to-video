"""
Audio Agent — agent.py
Contains voice synthesis logic extracted from agents/studio_workers.py.
Handles per-scene audio generation via the MCP voice_cloning_synthesizer tool,
including multi-line dialogue concatenation and WAV merging.

LangGraph node function exported:
    voice_synth_node(state) -> dict
"""

import wave
import logging
import os
import shutil
from typing import Any, Dict, List, Optional

logger = logging.getLogger("VoiceSynth")
from shared.utils.progress import report_progress


def _infer_emotion(line: str, visual_cue: Optional[str]) -> str:
    """
    Lightweight dialogue emotion tag for TTS (rate/pitch). Script JSON rarely includes `emotion`,
    so we infer from line text + visual_cue. Replace with LLM labeling in Scriptwriter for richer results.
    """
    blob = f"{line or ''} {visual_cue or ''}".lower()
    if any(
        w in blob
        for w in (
            "terrified",
            "scared",
            "fear",
            "panic",
            "trembling",
            "anxiety",
            "nervous",
            "worried",
            "please no",
            "don't hurt",
        )
    ):
        return "fearful"
    if any(
        w in blob
        for w in (
            "love",
            "wonderful",
            "great",
            "happy",
            "smile",
            "laugh",
            "joy",
            "yes!",
            "finally",
        )
    ):
        return "happy"
    if any(
        w in blob
        for w in (
            "cry",
            "tears",
            "sorry",
            "lost",
            "gone",
            "never see",
            "sad",
            "mourning",
            "devastated",
        )
    ):
        return "sad"
    if any(w in blob for w in ("whisper", "quiet", "calm", "soft", "slow breath", "steady")):
        return "calm"
    if any(
        w in blob
        for w in (
            "hate",
            "kill",
            "furious",
            "rage",
            "how dare",
            "damn it",
            "bastard",
            "vengeance",
            "shouting",
            "snarl",
            "growl",
        )
    ):
        return "angry"
    return "neutral"


from shared.schemas.phase2_state import StudioState


def _get_registry():
    """Lazily return the Phase 2 MCP registry singleton."""
    from mcp.tool_registry import registry
    return registry


def _char_db_by_name(character_db_list: List[Dict]) -> Dict[str, Dict]:
    """Convert character_db list to a dict keyed by character name."""
    return {c["name"]: c for c in character_db_list}


def _safe_tag(scene_id: int) -> str:
    return f"scene_{int(scene_id):02d}"


# ─────────────────────────────────────────────────────────────────────────────
# WAV utilities
# ─────────────────────────────────────────────────────────────────────────────

def _wav_duration(path: str) -> float:
    """Return duration of a WAV file in seconds."""
    try:
        with wave.open(path, "r") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


def _concat_wavs(paths: List[str], out_path: str) -> None:
    """
    Concatenate WAV/audio files into a single WAV.
    Tries: ffmpeg concat → soundfile/numpy → stdlib copy.
    """
    import subprocess
    import shutil

    valid_paths = [p for p in paths if os.path.exists(p)]
    if not valid_paths:
        return

    # Method 1: ffmpeg concat filter
    try:
        inputs = []
        filter_parts = []
        for i, p in enumerate(valid_paths):
            inputs += ["-i", p]
            filter_parts.append(f"[{i}:a]apad=pad_dur=0.3[a{i}]")
        concat_inputs = "".join(f"[a{i}]" for i in range(len(valid_paths)))
        filter_complex = (
            ";".join(filter_parts)
            + f";{concat_inputs}concat=n={len(valid_paths)}:v=0:a=1[out]"
        )
        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-ar", "16000", "-ac", "1",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return
    except Exception:
        pass

    # Method 2: soundfile + numpy
    try:
        import soundfile as sf
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
    shutil.copy2(valid_paths[0], out_path)


# ─────────────────────────────────────────────────────────────────────────────
# Voice Synthesis Node
# ─────────────────────────────────────────────────────────────────────────────

def _parse_line_with_sfx(text: str) -> List[Dict[str, str]]:
    """
    Split a dialogue line into 'speech' and 'sfx' segments.
    Example: "(laughs) Hello world" -> [{'type': 'sfx', 'val': 'laughs'}, {'type': 'speech', 'val': 'Hello world'}]
    """
    import re
    # Match (...) or [...]
    pattern = r"([\[\(].*?[\)\]])"
    parts = re.split(pattern, text)
    segments = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("(", "[")) and p.endswith((")", "]")):
            cue = p[1:-1].strip()
            if cue:
                segments.append({"type": "sfx", "val": cue})
        else:
            segments.append({"type": "speech", "val": p})
    return segments


def voice_synth_node(state: StudioState) -> dict:
    """
    Synthesizes per-scene audio via MCP voice_cloning_synthesizer tool.
    Handles parenthetical SFX (e.g. laughter) by fetching clips from Freesound.
    """
    registry = _get_registry()
    output_root = state.get("output_root", os.environ.get("PHASE2_OUTPUT_DIR", "data/outputs/phase2"))
    jobs = state.get("scene_jobs", [])
    character_db_list = state.get("character_db", [])
    char_db = _char_db_by_name(character_db_list) if character_db_list else {}

    audio_tracks: List[Dict[str, Any]] = []
    logs: List[Dict[str, Any]] = []

    for job in jobs:
        scene = job.get("scene", {})
        scene_id = int(job["scene_id"])
        report_progress("phase2", "Voice Synth", "running", f"Synthesizing audio for Scene {scene_id}...")
        logger.info(f"🎤 [VoiceSynth] Synthesizing audio for Scene {scene_id}...")
        scene_tag = _safe_tag(scene_id)
        dialogue_lines = scene.get("dialogue", [])

        segment_paths: List[str] = []
        temp_dir = os.path.join(output_root, "temp_audio", scene_tag)
        os.makedirs(temp_dir, exist_ok=True)

        for i, line in enumerate(dialogue_lines):
            speaker = line.get("speaker", "A")
            text = line.get("line") or ""
            emotion = line.get("emotion") or _infer_emotion(text, line.get("visual_cue"))
            char_info = char_db.get(speaker, {})
            
            # Split line into SFX and Speech
            segments = _parse_line_with_sfx(text)
            line_segments: List[str] = []
            
            for j, seg in enumerate(segments):
                seg_path = os.path.join(temp_dir, f"line_{i:02d}_seg_{j:02d}.wav")
                if seg["type"] == "sfx":
                    logger.info(f"🔊 [VoiceSynth] Fetching SFX for: {seg['val']}")
                    res = registry.invoke("sfx_tool", {"cue": seg["val"], "output_path": seg_path})
                    if res.get("ok"):
                        line_segments.append(seg_path)
                else:
                    logger.info(f"🗣️ [VoiceSynth] Synthesizing speech: {seg['val'][:30]}...")
                    try:
                        registry.invoke("voice_cloning_synthesizer", {
                            "character_name": speaker,
                            "dialogue": seg["val"],
                            "output_path": seg_path,
                            "reference_audio_path": char_info.get("reference_audio"),
                            "emotion": emotion,
                            "gender": char_info.get("gender"),
                            "edge_voice": char_info.get("edge_voice"),
                            "tts_voice": char_info.get("tts_voice"),
                            "kokoro_voice": char_info.get("kokoro_voice"),
                        })
                        if os.path.exists(seg_path):
                            line_segments.append(seg_path)
                    except Exception as e:
                        logger.warning(f"Speech synth failed for seg {j}: {e}")

            if line_segments:
                line_final = os.path.join(temp_dir, f"line_{i:02d}.wav")
                if len(line_segments) > 1:
                    _concat_wavs(line_segments, line_final)
                else:
                    # Just move/copy the single segment to the expected name
                    shutil.copy2(line_segments[0], line_final)
                segment_paths.append(line_final)

        combined_path = os.path.join(output_root, "audio_tracks", f"{scene_tag}.wav")
        os.makedirs(os.path.dirname(combined_path), exist_ok=True)

        if segment_paths:
            _concat_wavs(segment_paths, combined_path)
        else:
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
