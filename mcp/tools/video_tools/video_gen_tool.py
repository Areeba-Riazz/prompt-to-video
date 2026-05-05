import logging
import os
import random
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from mcp.base_tool import BaseTool
from shared.utils.llm_client import chat_text

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


def _pexels_pick_download_url(videos: List[dict], target_duration: float = 0) -> Tuple[str, str, float]:
    """
    Return (mp4_url, debug_label, actual_duration). 
    Prioritizes clips where duration >= target_duration.
    """
    # Sort by relevance (original Pexels order) but filter by duration if target_duration > 0
    candidates = []
    for vid in videos:
        files = vid.get("video_files") or []
        if not files:
            continue
        v_dur = vid.get("duration", 0)
        
        # If target_duration is set, we prefer clips that are long enough
        if target_duration > 0 and v_dur < target_duration:
            continue
            
        candidates.append(vid)

    # If no clips were long enough, just use all videos
    final_list = candidates if candidates else videos
    
    for vid in final_list:
        files = vid.get("video_files") or []
        if not files:
            continue
            
        v_dur = vid.get("duration", 0)
        # Find best resolution (1080p or higher)
        sorted_files = sorted(files, key=lambda f: f.get("width", 0), reverse=True)
        for vf in sorted_files:
            link = vf.get("link")
            if link:
                qual = f'{vf.get("quality", "?")} {vf.get("width", "?")}w'
                return link, qual, v_dur
                
    raise RuntimeError("No valid MP4 links found in Pexels results.")


def _generate_pexels_query(visual_cue: str, location: str, gender: str) -> str:
    """
    Two-tiered search query generation:
    1. LLM-Optimized (Primary)
    2. Rule-Based (Fallback)
    """
    # 1. LLM-Optimized Approach
    try:
        system_prompt = (
            "You are a cinematic video search expert. Generate a 5-8 word search query for Pexels stock video. "
            "Guidelines: NO character names. Use generic subjects like 'man', 'woman', or 'person'. "
            "Focus on action and environment. Match lighting/time of day to location. "
            "Return ONLY the query string, no quotes."
        )
        user_prompt = (
            f"Visual Cue: {visual_cue}\n"
            f"Location: {location}\n"
            f"Subject: {gender or 'person'}"
        )
        query = chat_text(system=system_prompt, user=user_prompt, temperature=0.3)
        if query and len(query.split()) >= 3:
            logger.info(f"[QueryGen] LLM generated: {query}")
            return query
    except Exception as e:
        logger.warning(f"QueryGen LLM failed: {e}")

    # 2. Fallback Rule-Based Approach
    logger.info("[QueryGen] Using rule-based fallback...")
    subject = f"one {gender or 'person'}"
    
    # Clean location (remove INT./EXT. and - DAY/NIGHT)
    clean_loc = location.upper().replace("INT.", "").replace("EXT.", "").strip()
    clean_loc = re.split(r"[-–]", clean_loc)[0].strip().lower()
    
    # Extract keywords from visual cue
    # Remove common filler words and action verbs that don't help stock search
    stop_verbs = ["slams", "leans", "looks", "walks", "stands", "sits", "sees", "hears"]
    cue_words = [w for w in visual_cue.lower().split() if w not in stop_verbs and len(w) > 3]
    keywords = " ".join(cue_words[:3])
    
    query = f"{subject} in {clean_loc} {keywords}".strip()
    logger.info(f"🛠️ [QueryGen] Rule-based result: {query}")
    return query


def _generate_pexels_stock(kwargs: Dict[str, Any], output_path: str) -> str:
    import requests

    api_key = _pexels_api_key()
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY missing")

    visual_cue = kwargs.get("visual_cue", "")
    location = kwargs.get("location", "")
    gender = kwargs.get("gender", "person")
    target_duration = float(kwargs.get("target_duration", 0))

    query = _generate_pexels_query(visual_cue, location, gender)
    headers = {"Authorization": api_key, "User-Agent": "prompt-to-video/1.0"}

    logger.info("Pexels search query=%r", query)
    videos, _ = _pexels_search(headers, query, "landscape")

    if not videos:
        logger.warning("Pexels empty for %r — trying fallback query", query)
        fallback_query = f"cinematic {location.lower()}"
        videos, _ = _pexels_search(headers, fallback_query, None)

    if not videos:
        raise RuntimeError(f"Pexels returned zero videos for {query}")

    url, qual, actual_dur = _pexels_pick_download_url(videos[:15], target_duration)
    logger.info("Pexels downloading %s (%s) -> %s", qual, url[:80], output_path)

    # Download
    dl_res = requests.get(url, stream=True, timeout=120)
    if dl_res.status_code != 200:
        raise RuntimeError(f"Pexels download failed HTTP {dl_res.status_code}")

    with open(output_path, "wb") as f:
        for chunk in dl_res.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

    # TRIMMING LOGIC: If clip is longer than target_duration, cut it
    if target_duration > 0 and actual_dur > target_duration + 0.1:
        logger.info(f"[VideoGen] Trimming clip from {actual_dur:.1f}s to {target_duration:.1f}s")
        tmp_trim = output_path + ".trim.mp4"
        try:
            subprocess.run([
                "ffmpeg", "-y",
                "-i", os.path.abspath(output_path),
                "-t", str(target_duration),
                "-c", "copy",
                os.path.abspath(tmp_trim)
            ], capture_output=True, check=True)
            if os.path.exists(tmp_trim):
                shutil.move(tmp_trim, output_path)
        except Exception as e:
            logger.warning(f"Trim failed: {e}")

    return output_path


def _pexels_search(headers: dict, query: str, orientation: Optional[str]) -> Tuple[List[dict], str]:
    import requests
    params: Dict[str, Any] = {"query": query, "per_page": 15}
    if orientation:
        params["orientation"] = orientation
    res = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=45)
    if res.status_code != 200:
        return [], query
    return res.json().get("videos") or [], query


class VideoGenerationTool(BaseTool):
    @property
    def name(self) -> str:
        return "generate_scene_video"

    @property
    def description(self) -> str:
        return "Generates a cinematic video clip using Pexels, DashScope, or HF models."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "scene_id": "int",
            "visual_cue": "str — description of action",
            "location": "str — e.g. INT. OFFICE - DAY",
            "gender": "str — man/woman/person",
            "target_duration": "float — desired length in seconds",
            "output_path": "str",
            "method": "str — pexels, dashscope, hf_ai",
            "character_image_path": "str",
            "scene_prompt": "str — fallback prompt for AI models",
        }

    def execute(self, **kwargs) -> Any:
        method = kwargs.get("method", "pexels")
        output_path = kwargs.get("output_path", "")
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        if method == "pexels":
            return _generate_pexels_stock(kwargs, output_path)
        
        # AI methods still use the full scene_prompt
        scene_prompt = kwargs.get("scene_prompt", "")
        if method == "dashscope":
            return _generate_with_wan(scene_prompt, output_path)
        if method == "hf_ai":
            return _generate_with_hf_api(scene_prompt, output_path)

        return _ultimate_video_fallback(kwargs.get("character_image_path"), output_path)


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
            urllib.request.urlretrieve(video_url, output_path)
            return output_path
        if status == "FAILED":
            raise RuntimeError(f"DashScope Task Failed: {status_rsp.message}")
        time.sleep(10)


def _generate_with_hf_api(scene_prompt: str, output_path: str) -> str:
    import requests
    import time
    hf_token = os.environ.get("HF_TOKEN", "").strip()
    if not hf_token:
        raise RuntimeError("HF_TOKEN missing")

    print(f"[VideoGen] Calling HF API (LTX-Video)...")
    API_URL = "https://api-inference.huggingface.co/models/Lightricks/LTX-Video"
    headers = {"Authorization": f"Bearer {hf_token}"}
    
    for attempt in range(3):
        response = requests.post(API_URL, headers=headers, json={"inputs": scene_prompt})
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        elif response.status_code == 503:
            time.sleep(20)
        else:
            raise RuntimeError(f"HF API Failed: {response.text}")
    raise RuntimeError("HF API failed after retries")


def _ultimate_video_fallback(character_image_path: Optional[str], output_path: str) -> str:
    import subprocess
    img = character_image_path if character_image_path and os.path.isfile(character_image_path) else None
    if img:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", os.path.abspath(img),
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black",
            "-t", "6", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-movflags", "+faststart",
            os.path.abspath(output_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=120)
        if os.path.exists(output_path):
            return output_path

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x151520:s=1280x720:d=6",
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-movflags", "+faststart",
        os.path.abspath(output_path),
    ], capture_output=True, timeout=60)
    return output_path
