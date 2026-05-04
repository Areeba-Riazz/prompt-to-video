import os
import shutil
import subprocess
from typing import Any, Dict, Optional
from mcp.base_tool import BaseTool


def _env_bool_use_ai_animation() -> bool:
    """
    SadTalker vs FFmpeg mux. Default True if unset (legacy behavior).
    Accepts: true/false, 1/0, yes/no, on/off (case-insensitive).
    """
    raw = os.environ.get("USE_AI_ANIMATION")
    if raw is None or raw.strip() == "":
        return True
    s = raw.strip().lower()
    if s in ("0", "false", "no", "off", "n"):
        return False
    if s in ("1", "true", "yes", "on", "y"):
        return True
    try:
        import ast

        return bool(ast.literal_eval(raw.strip().title()))
    except (ValueError, SyntaxError):
        print(f"[LipSync] Invalid USE_AI_ANIMATION={raw!r}; defaulting to FFmpeg mux (False).")
        return False


def _lip_sync_sadtalker_api(source_image: str, audio_path: str, output_path: str) -> str:
    try:
        from gradio_client import Client, handle_file
    except ImportError:
        raise RuntimeError("gradio_client not installed. Run: pip install gradio_client")

    space_id = os.environ.get("LIP_SYNC_SPACE_ID", "vinthre/SadTalker")
    hf_token = os.environ.get("HF_TOKEN", "")

    print(f"[LipSync] Calling SadTalker Space: {space_id}...")
    try:
        client = Client(space_id, hf_token=hf_token if hf_token else None) if "hf_token" in Client.__init__.__code__.co_varnames else Client(space_id, token=hf_token if hf_token else None)
        
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

def _lip_sync_ffmpeg_mux(video_path: str, audio_path: str, output_path: str) -> str:
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

class LipSyncTool(BaseTool):
    @property
    def name(self) -> str:
        return "lip_sync_aligner"

    @property
    def description(self) -> str:
        return (
            "Synchronizes audio with an AI face or via static audio mux. "
            "Uses SadTalker via HuggingFace Space API (if USE_AI_ANIMATION=true) or FFmpeg."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "video_path": "str — Target video",
            "audio_path": "str — Synthesized dialogue WAV",
            "output_path": "str — Final lip-synced MP4",
            "source_image": "str | None — Path to character portrait PNG. Required for SadTalker mode.",
        }

    @property
    def tags(self) -> list[str]:
        return ["audio", "video", "lip_sync"]

    def execute(self, **kwargs) -> Any:
        video_path = kwargs.get("video_path", "")
        audio_path = kwargs.get("audio_path", "")
        output_path = kwargs.get("output_path", "")
        source_image = kwargs.get("source_image")

        use_ai = _env_bool_use_ai_animation()
        print(
            "[LipSync] USE_AI_ANIMATION effective=True (SadTalker)"
            if use_ai
            else "[LipSync] USE_AI_ANIMATION effective=False (FFmpeg mux with stock video)"
        )

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        if use_ai and source_image and os.path.exists(source_image):
            try:
                return _lip_sync_sadtalker_api(source_image, audio_path, output_path)
            except Exception as e:
                print(f"[LipSync] SadTalker AI failed: {e}. Falling back to FFmpeg Mux...")

        try:
            return _lip_sync_ffmpeg_mux(video_path, audio_path, output_path)
        except Exception as e:
            print(f"[LipSync] FFmpeg Mux failed: {e}. Copying video without audio.")

        shutil.copy2(video_path, output_path)
        return output_path
