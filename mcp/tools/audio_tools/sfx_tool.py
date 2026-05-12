import os
import subprocess
import tempfile
import logging
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from mcp.base_tool import BaseTool
from shared.repo_paths import resolve_from_repo

logger = logging.getLogger("SFXTool")

FREESOUND_BASE = "https://freesound.org/apiv2"

# Stopwords dropped when splitting compound cues (still try full phrase first).
_STOP = frozenset({
    "and", "or", "the", "a", "an", "of", "to", "in", "on", "at", "for", "with",
    "from", "into", "some", "any", "no", "not", "then", "as", "by",
})

# If cue (or its tokens) contains this substring, append these broader searches after token tries.
_KEYWORD_FALLBACKS: List[tuple[str, tuple[str, ...]]] = [
    ("groan", ("groan", "groaning", "annoyed grunt", "displeased audience", "disgruntled sigh")),
    ("murmur", ("murmur", "murmuring", "quiet whispering", "crowd murmur", "ambient voices quiet")),
    ("murmer", ("murmur", "murmuring", "quiet whispering", "crowd murmur")),  # common typo "murmers"
    ("laugh", ("laughter", "chuckle", "giggle", "laughing crowd")),
    ("chuckle", ("chuckle", "laugh", "snicker")),
    ("sigh", ("sigh", "exhale", "disappointed breath")),
    ("gasp", ("gasp", "sharp inhale", "surprise breath")),
    ("clap", ("applause", "clapping", "audience clap")),
    ("boo", ("booing", "crowd disapproval", "heckle")),
    ("cheer", ("cheering", "crowd cheer", "applause celebration")),
    ("footstep", ("footsteps", "walking foley", "steps concrete")),
    ("door", ("door close", "door slam", "door creak")),
    ("phone", ("phone ring", "telephone ring", "mobile ring")),
    ("rain", ("rain", "rainfall", "rain ambient")),
    ("thunder", ("thunder", "thunderstorm rumble")),
]


def _tokenize_cue(cue: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", cue.lower()) if t]


def _singular_sfx_token(t: str) -> Optional[str]:
    """Cheap singular for plural cues (groans -> groan); skip very short stems."""
    if len(t) < 4 or not t.endswith("s"):
        return None
    stem = t[:-1]
    if len(stem) < 3:
        return None
    return stem


def freesound_query_variants(cue: str) -> List[str]:
    """
    Ordered search phrases for Freesound: exact cue, split compounds, tokens,
    singulars, then keyword-based broader queries. Deduplicated, stable order.
    """
    base = (cue or "").strip().lower()
    if not base:
        return []

    seen: set[str] = set()
    out: List[str] = []

    def add(q: str) -> None:
        q = " ".join(q.split())
        if len(q) < 2:
            return
        k = q.casefold()
        if k in seen:
            return
        seen.add(k)
        out.append(q)

    add(base)

    # "groans and murmur" -> "groans murmur"
    no_and = re.sub(r"\s+and\s+", " ", base)
    add(no_and)

    # Split on connectors: commas, semicolons, slash, "and"
    parts = re.split(r"\s*,\s*|\s*;\s*|\s*/\s*|\s+and\s+", base)
    for p in parts:
        p = p.strip()
        if p and p != base:
            add(p)

    tokens = [t for t in _tokenize_cue(base) if t not in _STOP and len(t) >= 2]
    uniq_tokens = list(dict.fromkeys(tokens))  # preserve order, unique

    for t in sorted(set(tokens), key=lambda x: (-len(x), x)):
        add(t)
        sg = _singular_sfx_token(t)
        if sg and sg not in _STOP:
            add(sg)

    if uniq_tokens:
        add(" ".join(uniq_tokens))

    haystack = f"{base} {' '.join(uniq_tokens)}"
    for needle, extras in _KEYWORD_FALLBACKS:
        if needle in haystack:
            for ex in extras:
                add(ex)

    if uniq_tokens:
        longest = max(uniq_tokens, key=len)
        add(f"{longest} sound effect")
        add(f"{longest} sfx")

    return out


def _normalize_env_token(raw: str) -> str:
    """Strip whitespace and common .env quoting so the Freesound token is valid."""
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def sfx_clip_seconds() -> float:
    """
    Max length (seconds) for Freesound SFX clips after download.
    Env SFX_CLIP_SECONDS — default 4; clamped to [3, 5] as a practical band.
    """
    try:
        v = float(os.environ.get("SFX_CLIP_SECONDS", "4"))
    except ValueError:
        v = 4.0
    return max(3.0, min(v, 5.0))


def and_separated_cue_parts(cue: str) -> Optional[List[str]]:
    """
    If cue uses ' ... and ... ', return the segments (e.g. ['groans', 'murmurs']).
    Otherwise None. Used to fetch overlapping layers when one combined clip fails.
    """
    raw = (cue or "").strip()
    if not raw or not re.search(r"\s+and\s+", raw, re.IGNORECASE):
        return None
    parts = re.split(r"\s+and\s+", raw.strip(), flags=re.IGNORECASE)
    out: List[str] = []
    for p in parts:
        p = " ".join(p.split()).lower()
        if len(p) >= 2:
            out.append(p)
    return out if len(out) >= 2 else None


class SFXTool(BaseTool):
    """
    SFX: local cache, then Freesound (multi-query + optional 'X and Y' overlap mix),
    trimmed to a few seconds, then silence. Set FREESOUND_API_KEY; optional SFX_CLIP_SECONDS (3–5).
    """

    @property
    def name(self) -> str:
        return "sfx_tool"

    @property
    def description(self) -> str:
        return (
            "Fetches SFX from Freesound: combined cue with fallbacks; if that fails and the cue "
            "contains ' and ', fetches each side and overlaps them. Clips are trimmed (~3–5 s). "
            "Requires FREESOUND_API_KEY."
        )

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

        cache_dir = resolve_from_repo(os.path.join("data", "temp", "sounds"))
        os.makedirs(cache_dir, exist_ok=True)

        clean_cue = re.sub(r"[^a-z0-9]", "_", cue)
        cached_file = os.path.join(cache_dir, f"{clean_cue}.wav")

        # 1. CACHE CHECK (delete cached wav under data/temp/sounds/ to force refetch)
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 1000:
            logger.info(f"[SFX] Using cached: {cue} ({cached_file})")
            shutil.copy2(cached_file, output_path)
            return {"ok": True, "output_path": output_path, "method": "cache"}

        # 2. FREESOUND
        api_key = _normalize_env_token(os.environ.get("FREESOUND_API_KEY", ""))
        if api_key:
            clip_sec = sfx_clip_seconds()
            try:
                search_q = self._freesound_try_one_cue(cue, api_key, cached_file, clip_sec)
                if search_q:
                    shutil.copy2(cached_file, output_path)
                    return {
                        "ok": True,
                        "output_path": output_path,
                        "method": "freesound",
                        "search_query": search_q,
                        "clip_seconds": clip_sec,
                    }

                # Combined clip failed — "groans and murmurs": fetch each part and overlap-mix
                parts = and_separated_cue_parts(cue)
                if parts:
                    logger.info(
                        f"[SFX] Combined search failed for {cue!r}; trying overlap mix for: {parts!r}"
                    )
                    stem_paths: List[str] = []
                    tmp_to_clean: List[str] = []
                    try:
                        for seg in parts:
                            fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
                            os.close(fd)
                            tmp_to_clean.append(tmp_wav)
                            sq = self._freesound_try_one_cue(seg, api_key, tmp_wav, clip_sec)
                            if sq:
                                stem_paths.append(tmp_wav)
                            else:
                                logger.warning(f"[SFX] No clip for segment {seg!r} in compound cue")
                        if len(stem_paths) >= 2 and self._mix_wavs_amix_overlap(stem_paths, cached_file):
                            shutil.copy2(cached_file, output_path)
                            return {
                                "ok": True,
                                "output_path": output_path,
                                "method": "freesound_mix",
                                "segments": parts,
                                "clip_seconds": clip_sec,
                            }
                        if len(stem_paths) == 1:
                            shutil.copy2(stem_paths[0], cached_file)
                            shutil.copy2(cached_file, output_path)
                            return {
                                "ok": True,
                                "output_path": output_path,
                                "method": "freesound_partial",
                                "segments": parts,
                                "clip_seconds": clip_sec,
                            }
                    finally:
                        for p in tmp_to_clean:
                            if os.path.exists(p):
                                try:
                                    os.remove(p)
                                except OSError:
                                    pass

                logger.warning(f"[SFX] No Freesound result for cue {cue!r}")
            except Exception as e:
                logger.warning(f"[SFX] Freesound failed: {e}")
        else:
            logger.info("[SFX] FREESOUND_API_KEY unset; skipping Freesound fetch")

        # 3. SILENCE
        return self._generate_silence(output_path)

    def _freesound_try_one_cue(
        self, cue: str, api_key: str, dest_wav: str, clip_sec: float
    ) -> Optional[str]:
        """Try Freesound variants for one cue; write dest_wav trimmed to clip_sec. Returns winning search_query or None."""
        variants = freesound_query_variants(cue)
        logger.info(f"[SFX] Freesound: {len(variants)} variant(s) for sub-cue {cue!r}")
        for vi, search_q in enumerate(variants):
            results: List[dict] = []
            for sort in ("rating_desc", "score"):
                results = self._freesound_search(
                    search_q, api_key, max_results=15, sort=sort
                )
                if results:
                    break
            if not results:
                continue
            logger.info(
                f"[SFX] Freesound query[{vi + 1}/{len(variants)}] {search_q!r} -> {len(results)} hit(s)"
            )
            for sound in results:
                preview_url = self._freesound_preview_url(sound)
                if not preview_url:
                    continue
                if self._download_preview_and_convert(
                    preview_url, dest_wav, max_duration_sec=clip_sec
                ):
                    return search_q
            logger.warning(
                f"[SFX] Hits for {search_q!r} but no preview converted; trying next variant…"
            )
        return None

    def _mix_wavs_amix_overlap(self, wav_paths: List[str], out_path: str) -> bool:
        """Overlap multiple mono WAVs (same rate) with ffmpeg amix — simultaneous blend."""
        n = len(wav_paths)
        if n < 2:
            return False
        try:
            cmd = ["ffmpeg", "-y"]
            for p in wav_paths:
                cmd += ["-i", p]
            ins = "".join(f"[{i}:a]" for i in range(n))
            fc = f"{ins}amix=inputs={n}:duration=longest:normalize=1:dropout_transition=2[aout]"
            cmd += [
                "-filter_complex",
                fc,
                "-map",
                "[aout]",
                "-ar",
                "16000",
                "-ac",
                "1",
                out_path,
            ]
            res = subprocess.run(cmd, capture_output=True, timeout=60)
            if res.returncode != 0 or not os.path.exists(out_path):
                err = (res.stderr or b"").decode(errors="ignore")[-400:]
                logger.warning(f"[SFX] amix overlap failed: {err}")
                return False
            return os.path.getsize(out_path) > 256
        except Exception as e:
            logger.error(f"[SFX] amix overlap error: {e}")
            return False

    def _freesound_search(
        self, query: str, api_key: str, max_results: int = 10, sort: str = "rating_desc"
    ) -> List[dict]:
        url = f"{FREESOUND_BASE}/search/text/"
        params = {
            "query": query,
            "token": api_key,
            "fields": "id,name,duration,download,previews,tags,avg_rating,num_ratings",
            "page_size": min(max(max_results, 1), 150),
            "sort": sort,
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    @staticmethod
    def _freesound_preview_url(sound: dict) -> Optional[str]:
        """
        Prefer MP3 previews first — many Windows ffmpeg builds decode MP3 reliably;
        OGG/Vorbis can fail if ffmpeg was built without libvorbis.
        """
        previews = sound.get("previews") or {}
        return (
            previews.get("preview-hq-mp3")
            or previews.get("preview-lq-mp3")
            or previews.get("preview-hq-ogg")
            or previews.get("preview-lq-ogg")
        )

    def _download_preview_and_convert(
        self, url: str, dest_wav: str, max_duration_sec: Optional[float] = None
    ) -> bool:
        ext = Path(url.split("?", 1)[0]).suffix.lower() or ".ogg"
        if ext not in (".ogg", ".mp3", ".wav", ".m4a", ".flac"):
            ext = ".ogg"
        tmp_name: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_name = tmp.name
            headers = {"User-Agent": "ProjectMontage/1.0 (SFXTool)"}
            with requests.get(url, headers=headers, stream=True, timeout=30) as resp:
                resp.raise_for_status()
                with open(tmp_name, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            cmd = ["ffmpeg", "-y", "-i", tmp_name, "-vn", "-ar", "16000", "-ac", "1"]
            if max_duration_sec is not None:
                cmd += ["-t", f"{float(max_duration_sec):.3f}"]
            cmd.append(dest_wav)
            res = subprocess.run(cmd, capture_output=True, timeout=30)
            if res.returncode != 0 or not os.path.exists(dest_wav):
                err = (res.stderr or b"").decode(errors="ignore")[-400:]
                logger.warning(f"[SFX] ffmpeg convert failed (return {res.returncode}): {err}")
                return False
            return True
        except Exception as e:
            logger.error(f"[SFX] Download/convert failed: {e}")
            return False
        finally:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

    def _generate_silence(self, output_path: str) -> Dict[str, Any]:
        try:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.5", output_path]
            subprocess.run(cmd, capture_output=True, timeout=10)
            return {"ok": True, "output_path": output_path, "method": "silence"}
        except Exception:
            return {"ok": False}
