"""
SubtitleTool — mcp/tools/video_tools/subtitle_tool.py

Burns subtitle text into a video using FFmpeg.
Now with accurate timing derived from actual audio/video files and xfade compensation.

Inputs
------
video_path   : str — source video
output_path  : str — destination video with burned-in subtitles
subtitles    : list[dict] — [{start_ms, end_ms, text}, ...] (takes priority)
srt_path     : str — path to existing .srt file (used when subtitles list absent)
font_size    : int — subtitle font size (default: 18)
font_color   : str — hex colour without '#' (default: "ffffff")
outline_color: str — hex colour for outline (default: "000000")
position     : str — "bottom" | "top"  (default: "bottom")
"""

import os
import re
import subprocess
import tempfile
import wave
from typing import Any, Dict, List, Optional

from mcp.base_tool import BaseTool


# ─────────────────────────────────────────────────────────────────────────────
# Timing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _wav_duration_s(path: str) -> float:
    """Read WAV duration in seconds via wave module."""
    try:
        with wave.open(path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 0.0


def _probe_mp4_duration_s(path: str) -> float:
    """Probe MP4 duration in seconds via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _scene_tag(scene_id: int) -> str:
    """Return scene tag format: 'scene_01'."""
    return f"scene_{int(scene_id):02d}"


# ─────────────────────────────────────────────────────────────────────────────
# SRT helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ms_to_srt_ts(ms: int) -> str:
    """Convert milliseconds to SRT timestamp: HH:MM:SS,mmm"""
    ms = max(0, int(ms))
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _build_srt(subtitles: List[Dict]) -> str:
    """Build SRT file content from a list of {start_ms, end_ms, text} dicts."""
    lines = []
    for i, entry in enumerate(subtitles, start=1):
        start = entry.get("start_ms", 0)
        end = entry.get("end_ms", start + 2000)
        text = str(entry.get("text", "")).strip()
        if not text:
            continue
        lines.append(str(i))
        lines.append(f"{_ms_to_srt_ts(start)} --> {_ms_to_srt_ts(end)}")
        lines.append(text)
        lines.append("")  # blank separator
    return "\n".join(lines)


def _write_srt(subtitles: List[Dict], path: str) -> None:
    content = _build_srt(subtitles)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ─────────────────────────────────────────────────────────────────────────────
# Scene dialogue → subtitle entries
# ─────────────────────────────────────────────────────────────────────────────

def build_subtitle_manifest(
    scenes: List[Dict],
    output_root: Optional[str] = None,
    transition_duration: float = 0.5,
    words_per_minute: int = 130
) -> List[Dict]:
    """
    Builds accurate subtitle entries by:
    1. Probing actual WAV line durations from temp_audio/ (if output_root provided)
    2. Probing actual MP4 scene durations from final_scenes/
    3. Compensating for xfade overlap at scene boundaries.
    """
    entries = []
    cursor_s = 0.0

    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id") or scene.get("id") or (i + 1)
        scene_tag = _scene_tag(scene_id)
        
        # Determine actual scene start offset accounting for xfade
        overlap = transition_duration if i > 0 else 0.0
        scene_start_s = cursor_s - overlap
        
        # Probe actual video duration if possible
        actual_video_dur = 0.0
        if output_root:
            mp4_path = os.path.join(output_root, "final_scenes", f"scene_{scene_id}.mp4")
            actual_video_dur = _probe_mp4_duration_s(mp4_path)
        
        # Process dialogue lines
        line_cursor_s = 0.0
        dialogue_lines = scene.get("dialogue", [])
        
        for j, dlg in enumerate(dialogue_lines):
            line_text = dlg.get("line", "").strip()
            if not line_text:
                continue
            
            # 1. Get duration
            line_dur = 0.0
            if output_root:
                wav_path = os.path.join(output_root, "temp_audio", scene_tag, f"line_{j:02d}.wav")
                line_dur = _wav_duration_s(wav_path)
            
            # Fallback to estimate if WAV missing
            if line_dur <= 0:
                word_count = len(line_text.split())
                line_dur = max(1.5, word_count / words_per_minute * 60)
            
            start_abs = scene_start_s + line_cursor_s
            end_abs = start_abs + line_dur
            
            speaker = dlg.get("speaker", "")
            display_text = f"{speaker}: {line_text}" if speaker else line_text
            
            entries.append({
                "start_ms": int(start_abs * 1000),
                "end_ms": int(end_abs * 1000),
                "text": display_text,
            })
            
            # Advance line cursor (matching 0.3s gap in audio_agent/agent.py)
            line_cursor_s += line_dur + 0.3
            
        # Advance global cursor by actual video duration or sum of lines
        if actual_video_dur > 0:
            cursor_s += actual_video_dur
        else:
            cursor_s += line_cursor_s + 0.2 # small buffer

    return entries


def subtitles_from_scenes(scenes: List[Dict], words_per_minute: int = 130) -> List[Dict]:
    """Legacy wrapper for build_subtitle_manifest without file probing."""
    return build_subtitle_manifest(scenes, words_per_minute=words_per_minute)


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg burn-in
# ─────────────────────────────────────────────────────────────────────────────

def burn_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_size: int = 18,
    font_color: str = "ffffff",
    outline_color: str = "000000",
    position: str = "bottom",
) -> Dict[str, Any]:
    """
    Burns subtitles from an SRT file into the video using FFmpeg subtitles filter.
    Falls back to drawtext-based approach if the subtitles filter fails.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Normalise SRT path for FFmpeg (Windows backslash → forward slash, escape colons)
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")

    y_expr = "(h-text_h-30)" if position == "bottom" else "30"

    # Primary: subtitles= filter (supports full SRT formatting)
    subtitle_filter = (
        f"subtitles='{srt_escaped}'"
        f":force_style='Fontsize={font_size},PrimaryColour=&H00{font_color[::-1][:6].upper()}&,"
        f"OutlineColour=&H00{outline_color[::-1][:6].upper()}&,Outline=2,Shadow=1,"
        f"Alignment=2'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600)

    if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return {"ok": True, "output_path": output_path, "method": "subtitles_filter"}

    stderr = result.stderr.decode(errors="ignore")
    print(f"[SubtitleTool] subtitles filter failed: {stderr[-300:]}. Trying drawtext fallback…")

    # Fallback: re-read SRT and use drawtext for each entry
    return _burn_with_drawtext(video_path, srt_path, output_path, font_size, font_color, y_expr)


def _burn_with_drawtext(
    video_path: str,
    srt_path: str,
    output_path: str,
    font_size: int,
    font_color: str,
    y_expr: str,
) -> Dict[str, Any]:
    """Fallback: parse SRT and build a drawtext filter chain."""
    import re

    with open(srt_path, encoding="utf-8") as f:
        raw = f.read()

    block_pattern = re.compile(
        r"\d+\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\Z)",
        re.DOTALL,
    )

    def _ts_to_sec(ts: str) -> float:
        h, m, rest = ts.split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

    filters = []
    for m in block_pattern.finditer(raw):
        start = _ts_to_sec(m.group(1))
        end = _ts_to_sec(m.group(2))
        text = m.group(3).replace("\n", " ").replace("'", "\\'").replace(":", "\\:")
        filters.append(
            f"drawtext=fontsize={font_size}:fontcolor=#{font_color}:x=(w-text_w)/2:y={y_expr}"
            f":text='{text}':enable='between(t,{start},{end})'"
            f":box=1:boxcolor=black@0.5:boxborderw=5"
        )

    if not filters:
        # No entries parsed — just copy
        import shutil
        shutil.copy2(video_path, output_path)
        return {"ok": True, "output_path": output_path, "method": "passthrough_no_subs"}

    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=600)
    if result.returncode == 0 and os.path.exists(output_path):
        return {"ok": True, "output_path": output_path, "method": "drawtext"}

    err = result.stderr.decode(errors="ignore")[-400:]
    return {"ok": False, "error": f"drawtext fallback failed: {err}"}


# ─────────────────────────────────────────────────────────────────────────────
# MCP Tool class
# ─────────────────────────────────────────────────────────────────────────────

class SubtitleTool(BaseTool):
    """
    Burns subtitle text directly into a video file (hardcoded subtitles).
    Accepts either a list of timed entries or a pre-built SRT file path.
    """

    @property
    def name(self) -> str:
        return "subtitle_tool"

    @property
    def description(self) -> str:
        return (
            "Burns subtitles into a video using FFmpeg. Accepts either a list of "
            "{start_ms, end_ms, text} entries or a path to an existing .srt file."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "video_path": "str — source video path",
            "output_path": "str — destination video path",
            "subtitles": "list[dict] — [{start_ms, end_ms, text}] (optional)",
            "srt_path": "str — path to .srt file (used if subtitles list absent)",
            "font_size": "int — font size (default: 18)",
            "font_color": "str — hex color without # (default: 'ffffff')",
            "outline_color": "str — hex outline color without # (default: '000000')",
            "position": "str — 'bottom' | 'top' (default: 'bottom')",
        }

    @property
    def tags(self) -> list:
        return ["video", "subtitle", "ffmpeg"]

    def execute(self, **kwargs) -> Any:
        video_path: str = kwargs.get("video_path", "")
        output_path: str = kwargs.get("output_path", "")
        subtitles: Optional[List[Dict]] = kwargs.get("subtitles")
        srt_path: Optional[str] = kwargs.get("srt_path")
        font_size: int = int(kwargs.get("font_size", 18))
        font_color: str = kwargs.get("font_color", "ffffff")
        outline_color: str = kwargs.get("outline_color", "000000")
        position: str = kwargs.get("position", "bottom")

        if not video_path or not os.path.exists(video_path):
            return {"ok": False, "error": f"video_path not found: {video_path!r}"}
        if not output_path:
            return {"ok": False, "error": "output_path is required"}

        # Resolve SRT file
        if subtitles:
            # Write temp SRT from provided entries
            tmp_srt = output_path.replace(".mp4", "_subtitles.srt")
            _write_srt(subtitles, tmp_srt)
            srt_path = tmp_srt
        elif srt_path and not os.path.exists(srt_path):
            return {"ok": False, "error": f"srt_path not found: {srt_path!r}"}
        elif not srt_path:
            return {"ok": False, "error": "Either 'subtitles' list or 'srt_path' must be provided"}

        print(f"[SubtitleTool] Burning subtitles into {os.path.basename(video_path)}")
        result = burn_subtitles(
            video_path=video_path,
            srt_path=srt_path,
            output_path=output_path,
            font_size=font_size,
            font_color=font_color,
            outline_color=outline_color,
            position=position,
        )
        return result
