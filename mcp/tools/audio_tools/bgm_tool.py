"""
BGMTool — mcp/tools/audio_tools/bgm_tool.py

Selects or synthesises background music for a scene mood, then mixes it
under the existing video dialogue at a low volume using FFmpeg amix.

Mood → Track mapping
--------------------
Built-in synthesized ambient pads are generated via Python's wave module
(same pattern as the TTS tone fallback) — no external dependencies needed.

If FREESOUND_API_KEY is set in environment, the tool will also attempt to
download a matching free track from Freesound.org as the primary source.

Inputs
------
video_path   : str  — video file with dialogue audio
output_path  : str  — destination video with BGM mixed in
mood         : str  — "happy" | "sad" | "tense" | "calm" | "epic" | "neutral"
volume       : float— BGM volume relative to dialogue (default: 0.12)
loop_bgm     : bool — loop BGM to match video duration (default: True)
freesound_query_boost : str — optional extra Freesound search text (locations, style); from shared.bgm_plan
"""

import logging
import math
import os
import random
import shutil
import struct
import subprocess
import tempfile
import wave
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from mcp.base_tool import BaseTool

logger = logging.getLogger("BGMTool")


# ─────────────────────────────────────────────────────────────────────────────
# Synthesised ambient pad generator
# ─────────────────────────────────────────────────────────────────────────────

# Mood → (base_freq_hz, chord_intervals_semitones, tempo_bpm)
MOOD_PAD_CONFIG: Dict[str, Dict] = {
    "happy":   {"freq": 261.63, "intervals": [0, 4, 7, 12], "tempo": 120, "amplitude": 10000},
    "sad":     {"freq": 220.00, "intervals": [0, 3, 7, 10], "tempo": 60,  "amplitude": 8000},
    "tense":   {"freq": 246.94, "intervals": [0, 1, 6, 10], "tempo": 140, "amplitude": 12000},
    "calm":    {"freq": 174.61, "intervals": [0, 4, 7, 11], "tempo": 55,  "amplitude": 7000},
    "epic":    {"freq": 196.00, "intervals": [0, 7, 12, 19],"tempo": 100, "amplitude": 14000},
    "neutral": {"freq": 220.00, "intervals": [0, 4, 7],     "tempo": 75,  "amplitude": 8000},
}


def _semitone_ratio(semitones: int) -> float:
    return 2.0 ** (semitones / 12.0)


def _synthesise_pad(mood: str, duration_s: float, output_path: str) -> str:
    """
    Generate a simple ambient chord pad WAV using Python's wave module.
    Multiple sine waves are summed for a lush, chord-like texture.
    An envelope (attack/release) is applied for smoothness.
    """
    cfg = MOOD_PAD_CONFIG.get(mood, MOOD_PAD_CONFIG["neutral"])
    framerate = 44100
    n_frames = int(duration_s * framerate)
    base_freq: float = cfg["freq"]
    intervals: List[int] = cfg["intervals"]
    amplitude: int = cfg["amplitude"]
    # Slow LFO for vibrato / chorus-like effect
    lfo_rate = 0.25  # Hz
    lfo_depth = 0.015  # ±1.5% pitch variation

    # Attack / release envelope (10% each)
    attack_frames = int(n_frames * 0.10)
    release_frames = int(n_frames * 0.10)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)

        for i in range(n_frames):
            t = i / framerate
            # LFO modulation
            lfo = 1.0 + lfo_depth * math.sin(2 * math.pi * lfo_rate * t)
            # Sum all chord tones
            sample = 0.0
            for semitones in intervals:
                freq = base_freq * _semitone_ratio(semitones) * lfo
                sample += math.sin(2 * math.pi * freq * t)
            # Normalise by number of tones
            sample /= len(intervals)
            # Envelope
            if i < attack_frames:
                env = i / attack_frames
            elif i >= n_frames - release_frames:
                env = (n_frames - i) / release_frames
            else:
                env = 1.0
            val = int(amplitude * sample * env)
            val = max(-32767, min(32767, val))
            wf.writeframesraw(struct.pack("<h", val))

    return output_path


def _probe_video_duration(video_path: str) -> float:
    """Return video duration in seconds."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            timeout=30,
        )
        return float(result.stdout.decode().strip())
    except Exception:
        return 30.0


# ─────────────────────────────────────────────────────────────────────────────
# Optional Freesound download
# ─────────────────────────────────────────────────────────────────────────────

MOOD_FREESOUND_QUERY: Dict[str, str] = {
    "happy":   "uplifting ambient music",
    "sad":     "melancholy ambient piano",
    "tense":   "tense cinematic drone",
    "calm":    "calm nature ambient",
    "epic":    "epic orchestral music",
    "neutral": "ambient background music",
}


def _try_freesound_download(
    mood: str,
    dest_path: str,
    query_boost: str = "",
    *,
    vary_pick: bool = False,
) -> bool:
    """
    Try to download a mood-matched track from Freesound.
    query_boost: extra words from story (locations, style) appended to the mood baseline query.
    """
    api_key = os.environ.get("FREESOUND_API_KEY", "").strip()
    if not api_key:
        return False
    try:
        import json as _json
        import urllib.request

        base = MOOD_FREESOUND_QUERY.get(mood, "ambient music")
        extra = (query_boost or "").strip()
        query = f"{base} {extra}".strip() if extra else base
        query = " ".join(query.split())[:200]

        params = {
            "query": query,
            "fields": "id,name,previews",
            "filter": "duration:[5 TO 120]",
            "page_size": "8",
            "token": api_key,
        }
        url = "https://freesound.org/apiv2/search/text/?" + urlencode(params)
        logger.info("[BGM] Freesound search: %s", query[:120])
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = _json.loads(resp.read())

        results = data.get("results", [])
        if not results:
            return False

        candidates: List[str] = []
        for hit in results[:12]:
            previews = hit.get("previews") or {}
            url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
            if url:
                candidates.append(url)
        if not candidates:
            return False

        pool = candidates[: min(5, len(candidates))]
        preview_url = random.choice(pool) if vary_pick else pool[0]

        mp3_path = dest_path.replace(".wav", ".mp3")
        urllib.request.urlretrieve(preview_url, mp3_path)

        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-ar", "44100", "-ac", "1", dest_path],
            capture_output=True,
            timeout=60,
        )
        try:
            os.remove(mp3_path)
        except OSError:
            pass
        return result.returncode == 0 and os.path.exists(dest_path)
    except Exception as e:
        logger.warning("[BGM] Freesound download failed: %s", e)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg audio mixing
# ─────────────────────────────────────────────────────────────────────────────

def _mix_bgm_into_video(
    video_path: str,
    bgm_wav: str,
    output_path: str,
    bgm_volume: float,
    loop_bgm: bool,
) -> Dict[str, Any]:
    """
    Mix BGM at bgm_volume (0.0–1.0) under the video's existing audio using
    FFmpeg amix filter. Dialogue is kept at full volume; BGM is attenuated.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    loop_flag = ["-stream_loop", "-1"] if loop_bgm else []

    # amix: input 0 = original audio (weight 1.0), input 1 = BGM (weight bgm_volume)
    # duration=first ensures output matches video length
    filter_complex = (
        f"[0:a]volume=1.0[dialogue];"
        f"[1:a]volume={bgm_volume}[bgm];"
        f"[dialogue][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        *loop_flag,
        "-i", bgm_wav,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, timeout=600)
    if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return {"ok": True, "output_path": output_path}

    err = result.stderr.decode(errors="ignore")[-500:]
    return {"ok": False, "error": f"FFmpeg BGM mix failed: {err}"}


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool class
# ─────────────────────────────────────────────────────────────────────────────

class BGMTool(BaseTool):
    """
    Mixes story-aware background music into a video (Freesound + mood pad fallback).
    Pass freesound_query_boost from shared.bgm_plan.plan_bgm for scene-tailored searches.
    """

    @property
    def name(self) -> str:
        return "bgm_tool"

    @property
    def description(self) -> str:
        return (
            "Selects or synthesises background music for the given mood and mixes it "
            "into the video at a low volume using FFmpeg amix, preserving dialogue clarity."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "video_path": "str — source video file",
            "output_path": "str — destination video with BGM mixed in",
            "mood": "str — happy | sad | tense | calm | epic | neutral (default: neutral)",
            "volume": "float — BGM volume 0.0–1.0 (default: 0.12)",
            "loop_bgm": "bool — loop BGM to fill video duration (default: True)",
            "freesound_query_boost": "str — optional extra Freesound search words (locations, style)",
            "vary_freesound_pick": "bool — pick randomly among top Freesound previews (e.g. BGM re-roll)",
        }

    @property
    def tags(self) -> list:
        return ["audio", "bgm", "ffmpeg", "music"]

    def execute(self, **kwargs) -> Any:
        video_path: str = kwargs.get("video_path", "")
        output_path: str = kwargs.get("output_path", "")
        mood: str = kwargs.get("mood", "neutral").lower()
        volume: float = float(kwargs.get("volume", 0.12))
        loop_bgm: bool = bool(kwargs.get("loop_bgm", True))
        query_boost: str = str(kwargs.get("freesound_query_boost", "") or "").strip()
        vary_pick: bool = bool(kwargs.get("vary_freesound_pick", False))

        if not video_path or not os.path.exists(video_path):
            return {"ok": False, "error": f"video_path not found: {video_path!r}"}
        if not output_path:
            return {"ok": False, "error": "output_path is required"}

        # Clamp mood to known values
        if mood not in MOOD_PAD_CONFIG:
            mood = "neutral"

        duration = _probe_video_duration(video_path)
        # Add 5 s padding so BGM doesn't cut off abruptly at end
        pad_duration = duration + 5.0

        logger.info(
            "[BGM] duration=%.1fs mood=%s volume=%.3f boost=%r",
            duration,
            mood,
            volume,
            query_boost[:80] if query_boost else "",
        )

        used_freesound = False
        with tempfile.TemporaryDirectory() as work_dir:
            bgm_path = os.path.join(work_dir, f"bgm_{mood}.wav")

            if _try_freesound_download(mood, bgm_path, query_boost=query_boost, vary_pick=vary_pick):
                used_freesound = True
            else:
                logger.info("[BGM] Synthesising ambient pad for mood %r", mood)
                _synthesise_pad(mood, pad_duration, bgm_path)

            result = _mix_bgm_into_video(
                video_path=video_path,
                bgm_wav=bgm_path,
                output_path=output_path,
                bgm_volume=volume,
                loop_bgm=loop_bgm,
            )

        if not result.get("ok"):
            err = result.get("error", "unknown")
            logger.warning("[BGM] Mix failed (%s); not overwriting output.", err)
            return {"ok": False, "error": err}

        logger.info("[BGM] mixed into %s", os.path.basename(output_path))
        method = "freesound" if used_freesound else "synthesised_pad"
        return {
            "ok": True,
            "output_path": output_path,
            "mood": mood,
            "volume": volume,
            "method": method,
        }
