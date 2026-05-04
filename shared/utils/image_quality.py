"""Shared checks so we do not treat small compressible PNGs as failures everywhere."""

import os


def is_acceptable_portrait_png(
    path: str,
    min_side: int = 512,
    min_bytes: int = 10000,
) -> bool:
    """
    True if file looks like a real 768-class portrait, not an API error blob or our PIL placeholder.

    (Flux / SD can emit sharp PNGs under 120KB; byte-only thresholds caused false rejections.)
    """
    if not path or not os.path.isfile(path):
        return False
    try:
        if os.path.getsize(path) < min_bytes:
            return False
    except OSError:
        return False
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            w, h = im.size
        return min(w, h) >= min_side
    except Exception:
        return False


def truncate_prompt_for_get_url(prompt: str, max_chars: int = 1100) -> str:
    """Pollinations uses a GET URL; very long prompts are truncated or rejected by proxies/CDNs."""
    p = (prompt or "").strip()
    if len(p) <= max_chars:
        return p
    cut = p[: max_chars - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip() + "…"
