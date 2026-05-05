"""
CompositorTool — mcp/tools/video_tools/compositor_tool.py

Merges all scene_*.mp4 files from a directory into a single final_output.mp4.
Supports optional cross-dissolve (xfade) transitions between scenes.

Inputs
------
scene_dir        : str  — path to folder containing scene_*.mp4 files
output_path      : str  — destination path for final_output.mp4
transition       : str  — "none" | "fade" | "xfade"  (default: "xfade")
transition_duration : float — seconds for each transition (default: 0.5)
"""

import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

from mcp.base_tool import BaseTool


def _sorted_scene_files(scene_dir: str) -> List[str]:
    """Return scene_*.mp4 files sorted numerically by scene number."""
    pattern = re.compile(r"^scene_(\d+)\.mp4$")
    entries = []
    for f in os.listdir(scene_dir):
        m = pattern.match(f)
        if m:
            entries.append((int(m.group(1)), os.path.join(scene_dir, f)))
    entries.sort(key=lambda x: x[0])
    return [path for _, path in entries]


def _probe_duration(path: str) -> float:
    """Return video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
        val = result.stdout.decode().strip().split("\n")[0]
        return float(val)
    except Exception:
        return 0.0


def _get_video_info(path: str) -> Dict[str, Any]:
    """Probe video width, height, fps."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "default=noprint_wrappers=1",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
        info = {}
        for line in result.stdout.decode().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = v.strip()
        w = int(info.get("width", 1280))
        h = int(info.get("height", 720))
        fps_raw = info.get("r_frame_rate", "25/1")
        if "/" in fps_raw:
            num, den = fps_raw.split("/")
            fps = float(num) / float(den) if float(den) else 25.0
        else:
            fps = float(fps_raw)
        return {"width": w, "height": h, "fps": fps}
    except Exception:
        return {"width": 1280, "height": 720, "fps": 25.0}


def _normalise_clips(
    clips: List[str],
    work_dir: str,
    target_width: int,
    target_height: int,
    target_fps: float,
) -> List[str]:
    """
    Re-encode each clip to a common resolution/fps/codec so xfade can work.
    Returns list of normalised paths in work_dir.
    """
    normalised = []
    for i, clip in enumerate(clips):
        out = os.path.join(work_dir, f"norm_{i:03d}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-i", clip,
            "-vf", f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,fps={target_fps}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            out,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0 or not os.path.exists(out):
            err = result.stderr.decode(errors="ignore")[-400:]
            raise RuntimeError(f"Normalisation failed for {clip}: {err}")
        normalised.append(out)
    return normalised


def _concat_no_transition(clips: List[str], output_path: str) -> None:
    """Fast concat using concat demuxer (no re-encode if codecs match)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for clip in clips:
            f.write(f"file '{clip.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n")
        list_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            err = result.stderr.decode(errors="ignore")[-600:]
            raise RuntimeError(f"Concat failed: {err}")
    finally:
        try:
            os.remove(list_file)
        except OSError:
            pass


def _concat_with_xfade(
    clips: List[str],
    output_path: str,
    td: float,
    work_dir: str,
    target_width: int,
    target_height: int,
    target_fps: float,
) -> None:
    """
    Build a complex xfade filter graph for cross-dissolve transitions.
    All clips are first normalised to the same codec/res/fps.
    """
    normed = _normalise_clips(clips, work_dir, target_width, target_height, target_fps)
    n = len(normed)

    if n == 1:
        shutil.copy2(normed[0], output_path)
        return

    # Build ffmpeg input args
    inputs: List[str] = []
    for clip in normed:
        inputs += ["-i", clip]

    # Build complex filter: chain xfade + acrossfade
    # Durations per clip (after normalisation)
    durations = [_probe_duration(c) for c in normed]

    filter_parts: List[str] = []
    audio_parts: List[str] = []

    # Running offset (when the transition starts for each pair)
    # xfade_offset[i] = sum(durations[0..i]) - (i+1)*td
    v_label = "[0:v]"
    a_label = "[0:a]"

    for i in range(1, n):
        # Offset = cumulative duration of previous clips minus overlaps already consumed
        offset = sum(durations[:i]) - i * td
        offset = max(0.0, round(offset, 3))

        next_v = f"[{i}:v]"
        next_a = f"[{i}:a]"
        out_v = f"[vx{i}]"
        out_a = f"[ax{i}]"

        filter_parts.append(
            f"{v_label}{next_v}xfade=transition=fade:duration={td}:offset={offset}{out_v}"
        )
        audio_parts.append(
            f"{a_label}{next_a}acrossfade=d={td}{out_a}"
        )
        v_label = out_v
        a_label = out_a

    final_v = v_label
    final_a = a_label

    filter_graph = ";".join(filter_parts + audio_parts)
    filter_graph += f";{final_v}[vfinal];{final_a}[afinal]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", "[vfinal]",
        "-map", "[afinal]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=900)
    if result.returncode != 0:
        err = result.stderr.decode(errors="ignore")[-800:]
        # Fallback to simple concat if xfade fails (e.g. too many clips for memory)
        print(f"[Compositor] xfade failed ({err[:200]}). Falling back to simple concat.")
        _concat_no_transition(normed, output_path)


class CompositorTool(BaseTool):
    """
    Merges scene_*.mp4 files into a single final_output.mp4.
    Supports xfade (cross-dissolve), fade, or no transitions.
    """

    @property
    def name(self) -> str:
        return "compositor_tool"

    @property
    def description(self) -> str:
        return (
            "Merges all scene_*.mp4 files from scene_dir into a single final_output.mp4. "
            "Supports cross-dissolve (xfade) or fade transitions."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "scene_dir": "str — directory containing scene_*.mp4 files",
            "output_path": "str — destination path for final_output.mp4",
            "transition": "str — 'none' | 'fade' | 'xfade'  (default: 'xfade')",
            "transition_duration": "float — seconds per transition (default: 0.5)",
        }

    @property
    def tags(self) -> list:
        return ["video", "compositor", "ffmpeg"]

    def execute(self, **kwargs) -> Any:
        scene_dir: str = kwargs.get("scene_dir", "")
        output_path: str = kwargs.get("output_path", "")
        transition: str = kwargs.get("transition", "xfade")
        td: float = float(kwargs.get("transition_duration", 0.5))

        # Validate inputs
        if not scene_dir or not os.path.isdir(scene_dir):
            return {"ok": False, "error": f"scene_dir not found: {scene_dir!r}"}
        if not output_path:
            return {"ok": False, "error": "output_path is required"}

        clips = _sorted_scene_files(scene_dir)
        if not clips:
            return {"ok": False, "error": f"No scene_*.mp4 files found in {scene_dir}"}

        print(f"[Compositor] Found {len(clips)} scene clip(s): {[os.path.basename(c) for c in clips]}")
        print(f"[Compositor] Transition mode: {transition} | duration: {td}s")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if len(clips) == 1:
            # Nothing to merge — copy single clip
            shutil.copy2(clips[0], output_path)
            return {
                "ok": True,
                "output_path": output_path,
                "clips_merged": 1,
                "transition": "none (single clip)",
            }

        with tempfile.TemporaryDirectory() as work_dir:
            try:
                if transition in ("xfade", "fade"):
                    # Probe first clip for target resolution / fps
                    info = _get_video_info(clips[0])
                    _concat_with_xfade(
                        clips,
                        output_path,
                        td,
                        work_dir,
                        info["width"],
                        info["height"],
                        info["fps"],
                    )
                else:
                    _concat_no_transition(clips, output_path)
            except Exception as exc:
                # Last-resort: simple concat
                print(f"[Compositor] Primary strategy failed: {exc}. Falling back to simple concat.")
                try:
                    _concat_no_transition(clips, output_path)
                except Exception as exc2:
                    return {"ok": False, "error": str(exc2)}

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
            return {"ok": False, "error": "Output file missing or empty after composition"}

        size_mb = os.path.getsize(output_path) / 1_048_576
        print(f"[Compositor] [DONE] Final output: {output_path} ({size_mb:.1f} MB, {len(clips)} clips)")
        return {
            "ok": True,
            "output_path": output_path,
            "clips_merged": len(clips),
            "transition": transition,
            "size_mb": round(size_mb, 2),
        }
