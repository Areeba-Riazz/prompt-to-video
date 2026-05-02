"""
Video Generation — models/video_gen.py
MCP Tool Name: generate_scene_video

Supports generating videos via multiple engines natively for side-by-side comparison.
"""

import os
import random
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Engine 1: Wan2.1 via Alibaba DashScope API (Premium)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_with_wan(scene_prompt: str, output_path: str) -> str:
    import time
    import urllib.request
    try:
        from dashscope import VideoSynthesis
        import dashscope
    except ImportError:
        raise RuntimeError("dashscope not installed.")

    dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    print(f"[VideoGen] Calling DashScope Wan2.1 API...")
    
    rsp = VideoSynthesis.call(model='wan2.1-t2v-plus', prompt=scene_prompt, size='1280*720')
    if rsp.status_code != 200:
        raise RuntimeError(f"DashScope Wan2.1 failed: {rsp.message}")

    task_id = rsp.output.task_id
    while True:
        status_rsp = VideoSynthesis.wait(task_id=task_id)
        status = status_rsp.output.task_status
        if status == 'SUCCEEDED':
            video_url = status_rsp.output.video_url
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            urllib.request.urlretrieve(video_url, output_path)
            return output_path
        elif status == 'FAILED':
            raise RuntimeError(f"DashScope Task Failed: {status_rsp.message}")
        time.sleep(10)


# ─────────────────────────────────────────────────────────────────────────────
# Engine 2: HuggingFace LTX-Video Serverless API (Free AI fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_with_hf_api(scene_prompt: str, output_path: str) -> str:
    """
    Calls a HuggingFace free serverless API for text-to-video (e.g. LTX-Video).
    """
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
            # Model is loading
            err = response.json()
            wait_time = err.get("estimated_time", 20.0)
            print(f"[VideoGen] HF Model loading. Waiting {wait_time}s... (Attempt {attempt+1}/{max_retries})")
            time.sleep(min(wait_time + 5, 60))
        else:
            raise RuntimeError(f"HF API Failed ({response.status_code}): {response.text}")
            
    raise RuntimeError("HF API failed after maximum retries.")


# ─────────────────────────────────────────────────────────────────────────────
# Engine 3: Pexels Stock Footage (Free Stock fallback)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_pexels_stock(scene_prompt: str, output_path: str) -> str:
    """
    Downloads targeted stock footage from Pexels using the Visual Cue.
    """
    import requests
    import re
    
    api_key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PEXELS_API_KEY not set in .env")

    # Extract dynamic visual cue from prompt string
    # E.g. "Visual atmosphere: neon city night cyberpunk. Cinematic..."
    query = "cinematic scene"
    match = re.search(r"Visual atmosphere:\s*(.*?)\.\s*Cinematic", scene_prompt)
    if match:
        query = match.group(1).strip()

    print(f"[VideoGen] Searching Pexels accurately for: '{query}'...")
    headers = {"Authorization": api_key}
    res = requests.get(
        "https://api.pexels.com/videos/search",
        headers=headers,
        params={"query": query, "per_page": 10, "orientation": "landscape"}
    )
    
    if res.status_code != 200:
        raise RuntimeError(f"Pexels API error {res.status_code}")
        
    videos = res.json().get("videos", [])
    if not videos:
        print(f"[VideoGen] No results for '{query}'. Searching generic cinematic...")
        res = requests.get(
            "https://api.pexels.com/videos/search", headers=headers,
            params={"query": "cinematic beautiful", "per_page": 5}
        )
        videos = res.json().get("videos", [])
        if not videos:
            raise RuntimeError("Pexels returned zero videos.")
            
    video = random.choice(videos[:5])
    best_file = max(video.get("video_files", []), key=lambda f: f.get("width", 0))
    url = best_file["link"]
    
    print(f"[VideoGen] Downloading Pexels stock video to {output_path}...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    dl_res = requests.get(url, stream=True, headers={"User-Agent": "Mozilla/5.0"})
    if dl_res.status_code == 200:
        with open(output_path, 'wb') as f:
            for chunk in dl_res.iter_content(chunk_size=8192):
                if chunk: f.write(chunk)
        return output_path
    raise RuntimeError(f"Download failed {dl_res.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# MCP Public Output Tool
# ─────────────────────────────────────────────────────────────────────────────

def generate_scene_video(
    scene_id: int,
    scene_prompt: str,
    character_image_path: Optional[str],
    output_path: str,
    characters: list = [],
    method: str = "pexels"
) -> str:
    """
    Main entry point for generating video using a specified method.
    """
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
            print(f"[VideoGen] Pexels failed: {e}")
            
    # Ultimate Fallback: FFmpeg Black screen to prevent total cascade failure
    print(f"[VideoGen] Total generation failure. Padding black screen...")
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=5",
        "-c:v", "libx264", output_path
    ], capture_output=True)
    return output_path
