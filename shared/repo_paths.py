"""Resolve paths relative to the repository root so agents and the API work when cwd is backend/."""
from __future__ import annotations

import os

_SHARED_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_SHARED_DIR)


def resolve_from_repo(path: str) -> str:
    """If path is relative, join it to the repo root; absolute paths are normalized as-is."""
    if not path:
        return path
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(REPO_ROOT, expanded))
