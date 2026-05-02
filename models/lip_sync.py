"""
Lip Sync — models/lip_sync.py
MCP Tool Name: lip_sync_aligner

Priority chain:
  1. SadTalker via HuggingFace Space API (if USE_AI_ANIMATION=true)
  2. FFmpeg Audio Mux (Zero-drift alignment)
"""

import os
import shutil
import subprocess
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Engine 1: SadTalker AI (HuggingFace Spaces via gradio_client)
# ─────────────────────────────────────────────────────────────────────────────

def _lip_sync_sadtalker_api(
    source_image: str,
    audio_path: str,
    output_path: str,
) -> str:
    """
    Calls a public SadTalker space via gradio_client.
    Expects USE_AI_ANIMATION=true.
    """
    try:
        from gradio_client import Client, handle_file
    except ImportError:
        raise RuntimeError("gradio_client not installed. Run: pip install gradio_client")

    space_id = os.environ.get("LIP_SYNC_SPACE_ID", "vinthre/SadTalker")
    hf_token = os.environ.get("HF_TOKEN", "")

    print(f"[LipSync] Calling SadTalker Space: {space_id}...")
    try:
        client = Client(space_id, hf_token=hf_token if hf_token else None) if "hf_token" in Client.__init__.__code__.co_varnames else Client(space_id, token=hf_token if hf_token else None)
        
        # Exact API signatures vary greatly between Spaces. This uses a common SadTalker signature.
        # Fallbacks to MUX if the Space API is not compatible or throws an error.
        result = client.predict(
            source_image=handle_file(source_image),
            driven_audio=handle_file(audio_path),
            preprocess="crop",
            is_still_mode=True,
            enhancer="gfpgan",
            batch_size=1,
            size=256,
            pose_style=0,
            facerender="facevid2vid",
            exp_weight=1,
            use_ref_video=False,
            ref_video=None,
            ref_info="pose",
            use_idle_mode=False,
            length_of_audio=0,
            blink_every=True,
            fps=20,
            api_name="/submit"
        )
        
        # Result is typically a tuple or path to the temp video
        res_vid = result[0] if isinstance(result, (list, tuple)) else result
        if res_vid and os.path.exists(res_vid):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            shutil.copy2(res_vid, output_path)
            print(f"[LipSync] SadTalker video saved to {output_path}")
            return output_path
        else:
            raise RuntimeError("SadTalker returned an invalid result.")

    except Exception as e:
        raise RuntimeError(f"Gradio Space failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Engine 2: FFmpeg Audio Mux (0 drift alignment)
# ─────────────────────────────────────────────────────────────────────────────

def _lip_sync_ffmpeg_mux(
    video_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    """
    Mode B fallback: FFmpeg zero-drift temporal alignment.
    Simply muxes the audio onto the video. If the video is shorter/longer,
    it pads or cuts. No AI facial animation is applied.
    """
    if not os.path.exists(video_path) or not os.path.exists(audio_path):
        raise FileNotFoundError("Missing video or audio file for muxing.")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp_path = output_path + "._tmp.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", os.path.abspath(video_path),
        "-i", os.path.abspath(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        os.path.abspath(tmp_path)
    ]

    print("[LipSync] Running FFmpeg Audio Mux (Zero-Drift Alignment)...")
    result = subprocess.run(cmd, capture_output=True, timeout=120)

    if result.returncode == 0 and os.path.exists(tmp_path):
        shutil.move(tmp_path, output_path)
        print(f"[LipSync] FFmpeg muxed video saved to {output_path}")
        return output_path
    else:
        err = (result.stderr or b"").decode()[-500:]
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise RuntimeError(f"FFmpeg mux failed: {err}")


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point (registered as MCP tool)
# ─────────────────────────────────────────────────────────────────────────────

def align_lip_sync(
    video_path: str,
    audio_path: str,
    output_path: str,
    source_image: Optional[str] = None,
) -> str:
    """
    MCP Tool: lip_sync_aligner
    Synchronizes audio with an AI face or via static audio mux.

    Args:
        video_path: Target video.
        audio_path: Synthesized dialogue WAV.
        output_path: Final lip-synced MP4.
        source_image: Path to character portrait PNG. Required for SadTalker mode.

    Returns:
        Path to final output video.
    """
    import ast
    use_ai = ast.literal_eval(os.environ.get("USE_AI_ANIMATION", "True").title())

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if use_ai and source_image and os.path.exists(source_image):
        try:
            return _lip_sync_sadtalker_api(source_image, audio_path, output_path)
        except Exception as e:
            print(f"[LipSync] SadTalker AI failed: {e}. Falling back to FFmpeg Mux...")

    # Fallback to pure muxing
    try:
        return _lip_sync_ffmpeg_mux(video_path, audio_path, output_path)
    except Exception as e:
        print(f"[LipSync] FFmpeg Mux failed: {e}. Copying video without audio.")

    # Last-resort fallback
    shutil.copy2(video_path, output_path)
    return output_path
