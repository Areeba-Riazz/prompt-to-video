import os
import subprocess
import tempfile
import urllib.request
import logging
import shutil
import json
import re
import ssl
from typing import Any, Dict, List, Optional

from mcp.base_tool import BaseTool

logger = logging.getLogger("SFXTool")

# Wikimedia's primary IP for DNS fallback
WIKIMEDIA_IP = "208.80.154.224"

class SFXTool(BaseTool):
    """
    SFX Manager with Pixabay Video Audio Extraction and Wikimedia Fallback.
    1. Primary: Searches Pixabay Videos and extracts audio.
    2. Secondary: Wikimedia Search (with DNS-bypass IP fallback).
    """

    @property
    def name(self) -> str:
        return "sfx_tool"

    @property
    def description(self) -> str:
        return "Fetches SFX by extracting audio from Pixabay videos or Wikimedia Commons."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "cue": "str — the SFX cue (e.g. 'laughter')",
            "output_path": "str — destination path",
        }

    def execute(self, **kwargs) -> Any:
        cue = kwargs.get("cue", "").strip().lower()
        output_path = kwargs.get("output_path", "")
        if not cue or not output_path:
            return {"ok": False, "error": "Missing cue/output_path"}

        cache_dir = os.path.join("data", "temp", "sounds")
        os.makedirs(cache_dir, exist_ok=True)
        
        clean_cue = re.sub(r'[^a-z0-9]', '_', cue)
        cached_file = os.path.join(cache_dir, f"{clean_cue}.wav")
        
        # 1. CACHE CHECK
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 1000:
            logger.info(f"[SFX] Using cached: {cue}")
            shutil.copy2(cached_file, output_path)
            return {"ok": True, "output_path": output_path, "method": "cache"}

        # 2. METHOD 1: PIXABAY VIDEO AUDIO EXTRACTION
        pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
        if pixabay_key:
            logger.info(f"[SFX] Searching Pixabay Videos for: {cue}")
            try:
                # Search for videos matching the cue
                q = urllib.parse.quote(cue)
                url = f"https://pixabay.com/api/videos/?key={pixabay_key}&q={q}&per_page=3&safesearch=true"
                
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = json.loads(resp.read())
                
                hits = data.get("hits", [])
                if hits:
                    # Pick the best hit (one with a tiny video link)
                    # We use 'tiny' to save download time since we only need the audio
                    video_url = hits[0]["videos"].get("tiny", {}).get("url") or hits[0]["videos"].get("small", {}).get("url")
                    
                    if video_url:
                        logger.info(f"[SFX] Extracting audio from Pixabay video...")
                        if self._download_and_convert(video_url, cached_file):
                            shutil.copy2(cached_file, output_path)
                            return {"ok": True, "output_path": output_path, "method": "pixabay_video_extract"}
            except Exception as e:
                logger.warning(f"Pixabay extraction failed: {e}")

        # 3. METHOD 2: WIKIMEDIA SEARCH (DNS-BYPASS FALLBACK)
        logger.info(f"[SFX] Falling back to Wikimedia for: {cue}")
        download_url = self._search_wikimedia(cue)

        if download_url:
            if self._download_and_convert(download_url, cached_file):
                shutil.copy2(cached_file, output_path)
                return {"ok": True, "output_path": output_path, "method": "wikimedia"}

        # 4. FINAL FALLBACK: SILENCE
        return self._generate_silence(output_path)

    def _make_request(self, url: str) -> str:
        """Makes an HTTP request with DNS fallback to IP if needed."""
        headers = {'User-Agent': 'StudioFloor/1.0', 'Host': 'commons.wikimedia.org'}
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode('utf-8')
        except Exception as e:
            if "getaddrinfo failed" in str(e) or "NameResolutionError" in str(e):
                ip_url = url.replace("commons.wikimedia.org", WIKIMEDIA_IP)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                req = urllib.request.Request(ip_url, headers=headers)
                with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                    return resp.read().decode('utf-8')
            raise

    def _search_wikimedia(self, cue: str) -> Optional[str]:
        try:
            search_query = f"{cue} filetype:audio"
            api_url = (
                f"https://commons.wikimedia.org/w/api.php?action=query&list=search"
                f"&srsearch={search_query.replace(' ', '+')}&format=json&srlimit=1"
            )
            data = json.loads(self._make_request(api_url))
            results = data.get("query", {}).get("search", [])
            if not results: return None
            
            file_title = results[0]["title"]
            info_url = (
                f"https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo"
                f"&titles={file_title.replace(' ', '_')}&iiprop=url&format=json"
            )
            info_data = json.loads(self._make_request(info_url))
            pages = info_data.get("query", {}).get("pages", {})
            for page_id in pages:
                info = pages[page_id].get("imageinfo", [])
                if info: return info[0]["url"]
            return None
        except Exception as e:
            logger.error(f"Wikimedia search failed: {e}")
            return None

    def _download_and_convert(self, url: str, dest_path: str) -> bool:
        try:
            # Detect if this is a Wikimedia upload URL for Host header
            host = "upload.wikimedia.org" if "wikimedia.org" in url else None
            headers = {'User-Agent': 'StudioFloor/1.0'}
            if host: headers['Host'] = host
            
            tmp_name = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tmp:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        tmp.write(resp.read())
                    tmp_name = tmp.name
            except Exception as e:
                if host and ("getaddrinfo failed" in str(e)):
                    ip_url = url.replace(host, WIKIMEDIA_IP)
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    with tempfile.NamedTemporaryFile(suffix=".tmp", delete=False) as tmp:
                        req = urllib.request.Request(ip_url, headers=headers)
                        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                            tmp.write(resp.read())
                        tmp_name = tmp.name
                else: raise

            # Convert to 16k mono WAV and remove any video stream
            cmd = ["ffmpeg", "-y", "-i", tmp_name, "-vn", "-ar", "16000", "-ac", "1", dest_path]
            res = subprocess.run(cmd, capture_output=True, timeout=30)
            if tmp_name: os.remove(tmp_name)
            return res.returncode == 0 and os.path.exists(dest_path)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False

    def _generate_silence(self, output_path: str) -> Dict[str, Any]:
        try:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.5", output_path]
            subprocess.run(cmd, capture_output=True, timeout=10)
            return {"ok": True, "output_path": output_path, "method": "silence"}
        except: return {"ok": False}
