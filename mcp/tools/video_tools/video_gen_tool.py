import logging
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from mcp.base_tool import BaseTool

logger = logging.getLogger("VideoGenTool")


def _pexels_api_key() -> str:
    """Pexels expects the raw key in Authorization (no Bearer prefix)."""
    raw = (
        os.environ.get("PEXELS_API_KEY", "")
        or os.environ.get("PEXELS_KEY", "")
        or os.environ.get("PEXEL_API_KEY", "")
    )
    key = raw.strip().strip('"').strip("'").strip()
    return key


def _pexels_pick_download_url(videos: List[dict]) -> Tuple[str, str]:
    """Return (mp4_url, debug_label). Skip entries with empty video_files (was crashing max([]))."""
    random.shuffle(videos)
    for vid in videos:
        files = vid.get("video_files") or []
        if not files:
            logger.warning(
                "Pexels hit id=%s with no video_files (skip).",
                vid.get("id", "?"),
            )
            continue
        sorted_files = sorted(files, key=lambda f: f.get("width", 0), reverse=True)
        for vf in sorted_files:
            link = vf.get("link")
            if link:
                qual = f'{vf.get("quality", "?")} {vf.get("width", "?")}w'
                return link, qual
    raise RuntimeError(
        "Pexels returned videos but none had downloadable MP4 links (empty video_files). "
        "Try another query or check api.pexels.com status."
    )


def _pexels_search(headers: dict, query: str, orientation: Optional[str]) -> Tuple[List[dict], str]:
    import requests

    params: Dict[str, Any] = {"query": query, "per_page": 15}
    if orientation:
        params["orientation"] = orientation
    res = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params=params,
        timeout=45,
    )
    body_preview = (res.text or "")[:500]
    try:
        payload = res.json()
    except Exception:
        payload = {}

    if res.status_code == 401:
        raise RuntimeError(
            "Pexels returned 401 Unauthorized — key rejected or expired. "
            "Confirm PEXELS_API_KEY in .env (no 'Bearer ', no extra quotes), restart the API server."
        )
    if res.status_code == 429:
        raise RuntimeError("Pexels rate limit (429). Wait and retry.")
    if res.status_code != 200:
        raise RuntimeError(
            f"Pexels HTTP {res.status_code}: {payload.get('error', body_preview)}"
        )

    err_msg = payload.get("error")
    if err_msg:
        raise RuntimeError(f"Pexels API error: {err_msg}")

    return payload.get("videos") or [], query


def _generate_pexels_stock(scene_prompt: str, output_path: str) -> str:
    import re
    import requests

    api_key = _pexels_api_key()
    if not api_key:
        raise RuntimeError(
            "No Pexels key found. Set PEXELS_API_KEY in project-root .env and restart uvicorn "
            "(backend loads .env only at startup)."
        )

    query = "cinematic scene"
    match = re.search(r"Visual atmosphere:\s*(.*?)\.\s*Cinematic", scene_prompt, re.DOTALL)
    if match:
        inner = match.group(1).strip()
        if inner:
            query = inner[:200]

    headers = {"Authorization": api_key, "User-Agent": "prompt-to-video/1.0"}

    logger.info("Pexels search query=%r", query)
    videos, _ = _pexels_search(headers, query, "landscape")

    if not videos:
        logger.warning("Pexels empty for %r — retry without orientation filter.", query)
        videos, _ = _pexels_search(headers, query, None)

    if not videos:
        logger.warning("Pexels empty — fallback query cinematic nature city.")
        videos, _ = _pexels_search(headers, "cinematic nature city", None)

    if not videos:
        raise RuntimeError("Pexels returned zero videos for all tried queries.")

    url, qual = _pexels_pick_download_url(videos[:12])
    logger.info("Pexels downloading %s (%s) -> %s", qual, url[:80], output_path)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    dl_res = requests.get(
        url,
        stream=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; prompt-to-video/1.0)"},
        timeout=120,
    )
    if dl_res.status_code != 200:
        raise RuntimeError(f"Pexels CDN download failed HTTP {dl_res.status_code}")

    size = 0
    with open(output_path, "wb") as f:
        for chunk in dl_res.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                size += len(chunk)

    if size < 2000:
        raise RuntimeError(f"Pexels download too small ({size} bytes), likely not a valid MP4.")

    return output_path


def _generate_with_wan(scene_prompt: str, output_path: str) -> str:
    import time
    import urllib.request

    try:
        from dashscope import VideoSynthesis
        import dashscope
    except ImportError:
        raise RuntimeError("dashscope not installed.")

    dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    print("[VideoGen] Calling DashScope Wan2.1 API...")

    rsp = VideoSynthesis.call(model="wan2.1-t2v-plus", prompt=scene_prompt, size="1280*720")
    if rsp.status_code != 200:
        raise RuntimeError(f"DashScope Wan2.1 failed: {rsp.message}")

    task_id = rsp.output.task_id
    while True:
        status_rsp = VideoSynthesis.wait(task_id=task_id)
        status = status_rsp.output.task_status
        if status == "SUCCEEDED":
            video_url = status_rsp.output.video_url
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            urllib.request.urlretrieve(video_url, output_path)
            return output_path
        if status == "FAILED":
            raise RuntimeError(f"DashScope Task Failed: {status_rsp.message}")
        time.sleep(10)


def _generate_with_hf_api(scene_prompt: str, output_path: str) -> str:
    import requests
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if not hf_token:
        raise RuntimeError("HF_TOKEN missing in .env")

    import time
    
    print(f"[VideoGen] Calling HuggingFace Serverless API (LTX-Video)...")
    API_URL = "https://api-inference.huggingface.co/models/Lightricks/LTX-Video"
    headers = {"Authorization": f"Bearer {hf_token}"}
    
    max_retries = 3
    for attempt in range(max_retries):
        response = requests.post(API_URL, headers=headers, json={"inputs": scene_prompt})
        
        if response.status_code == 200:
            if response.headers.get("content-type", "").startswith("application/json"):
                err = response.json()
                print(f"[VideoGen] HF API JSON response (Not video): {err}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                    continue
                raise RuntimeError(f"HF API returned JSON instead of video: {err}")
            
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
            
        elif response.status_code == 503:
            err = response.json()
            wait_time = err.get("estimated_time", 20.0)
            print(f"[VideoGen] HF Model loading. Waiting {wait_time}s... (Attempt {attempt+1}/{max_retries})")
            time.sleep(min(wait_time + 5, 60))
        else:
            raise RuntimeError(f"HF API Failed ({response.status_code}): {response.text}")
            
    raise RuntimeError("HF API failed after maximum retries.")


class VideoGenerationTool(BaseTool):
    @property
    def name(self) -> str:
        return "generate_scene_video"

    @property
    def description(self) -> str:
        return (
            "Generates a video clip from a scene description and character image. "
            "Uses LTX-Video (GPU), Wan2.1 API, or Pexels stock (fallback)."
        )

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "scene_id": "int — scene number",
            "scene_prompt": "str — visual description of the scene",
            "character_image_path": "str | None — path to character portrait PNG",
            "output_path": "str — path to save output MP4",
            "method": "str — generation method: dashscope, hf_ai, pexels",
        }

    @property
    def tags(self) -> list[str]:
        return ["video", "video_gen"]

    def execute(self, **kwargs) -> Any:
        scene_id = kwargs.get("scene_id", 0)
        scene_prompt = kwargs.get("scene_prompt", "")
        character_image_path = kwargs.get("character_image_path")
        output_path = kwargs.get("output_path", "")
        method = kwargs.get("method", "pexels")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        if method == "dashscope":
            try:
                return _generate_with_wan(scene_prompt, output_path)
            except Exception as e:
                print(f"[VideoGen] DashScope failed: {e}")

        if method == "hf_ai":
            try:
                return _generate_with_hf_api(scene_prompt, output_path)
            except Exception as e:
                print(f"[VideoGen] HF API failed: {e}")

        if method == "pexels":
            try:
                return _generate_pexels_stock(scene_prompt, output_path)
            except Exception as e:
                logger.warning("Pexels failed: %s", e, exc_info=True)

        # Prefer a visible still from the Phase 1 portrait instead of a black clip (common cause of "all black" finals).
        return _ultimate_video_fallback(character_image_path, output_path)


def _ultimate_video_fallback(character_image_path: Optional[str], output_path: str) -> str:
    import subprocess

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img = character_image_path if character_image_path and os.path.isfile(character_image_path) else None
    if img:
        print("[VideoGen] API methods failed — using character portrait still clip (visible fallback).")
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            os.path.abspath(img),
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black",
            "-t",
            "6",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            os.path.abspath(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path
        err = (r.stderr or b"").decode(errors="ignore")[-400:]
        print(f"[VideoGen] Portrait-still ffmpeg failed: {err}")

    print("[VideoGen] No usable portrait — slate gray clip (avoid pure black).")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x151520:s=1280x720:d=6",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            os.path.abspath(output_path),
        ],
        capture_output=True,
        timeout=60,
    )
    return output_path
