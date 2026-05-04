"""Resolve media paths that may be stored relative to cwd or PHASE1_OUTPUT_DIR."""

from __future__ import annotations

import os
from typing import Optional


def resolve_media_path(path: Optional[str]) -> Optional[str]:
    """
    Return an absolute path to an existing file, or None.
    Tries: as given, then relative to cwd, then relative to PHASE1_OUTPUT_DIR.
    """
    if not path or not str(path).strip():
        return None
    raw = str(path).strip().strip('"').strip("'")
    if os.path.isabs(raw) and os.path.isfile(raw):
        return os.path.abspath(raw)
    if os.path.isfile(raw):
        return os.path.abspath(raw)
    phase1 = os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1")
    candidates = [
        os.path.join(os.getcwd(), raw),
        os.path.join(os.getcwd(), phase1, raw),
        os.path.join(os.getcwd(), phase1, os.path.basename(raw)),
        os.path.abspath(os.path.join(phase1, raw)),
    ]
    for cand in candidates:
        ap = os.path.normpath(cand)
        if os.path.isfile(ap):
            return ap
    return None
