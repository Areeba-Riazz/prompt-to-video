"""
State Manager — snapshot.py
Handles versioning, snapshotting, and reverting of the project state and assets.
"""

import os
import json
import shutil
import datetime
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("StateManager")

SNAPSHOT_DIR = "data/snapshots"
HISTORY_FILE = os.path.join(SNAPSHOT_DIR, "history.json")

class StateManager:
    @staticmethod
    def _ensure_dir():
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        if not os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "w") as f:
                json.dump([], f)

    @staticmethod
    def snapshot(version: str, state_json: Dict[str, Any], asset_paths: List[str], summary: str = "") -> Dict[str, Any]:
        """
        Saves a project snapshot.
        - version: e.g. "v1", "v2"
        - state_json: the full MontageState/StudioState dict
        - asset_paths: list of files to back up (copy to snapshot folder)
        """
        StateManager._ensure_dir()
        
        timestamp = datetime.datetime.now().isoformat()
        v_dir = os.path.join(SNAPSHOT_DIR, version)
        os.makedirs(v_dir, exist_ok=True)
        
        # 1. Save state
        state_file = os.path.join(v_dir, "state.json")
        with open(state_file, "w") as f:
            json.dump(state_json, f, indent=2)
            
        # 2. Backup assets (optional but recommended for full revert)
        backed_up_assets = []
        asset_dir = os.path.join(v_dir, "assets")
        os.makedirs(asset_dir, exist_ok=True)
        
        for path in asset_paths:
            if os.path.exists(path):
                rel_path = os.path.relpath(path, os.getcwd())
                # Create subdirs in asset_dir to match rel_path
                dest = os.path.join(asset_dir, rel_path)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy2(path, dest)
                backed_up_assets.append(rel_path)
        
        # 3. Update history
        entry = {
            "version": version,
            "timestamp": timestamp,
            "summary": summary,
            "state_path": state_file,
            "assets_count": len(backed_up_assets)
        }
        
        with open(HISTORY_FILE, "r+") as f:
            history = json.load(f)
            # Remove existing version if overwriting
            history = [h for h in history if h["version"] != version]
            history.append(entry)
            f.seek(0)
            json.dump(history, f, indent=2)
            f.truncate()
            
        logger.info(f"📸 [StateManager] Snapshot {version} saved with {len(backed_up_assets)} assets.")
        return entry

    @staticmethod
    def history() -> List[Dict[str, Any]]:
        """Returns the full list of snapshots."""
        StateManager._ensure_dir()
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)

    @staticmethod
    def truncate_future_after_version(branch_version: str) -> int:
        """
        Remove every snapshot strictly after ``branch_version`` in chronological
        (append) order — i.e. discard the redo branch when a new edit is saved
        from a past version.

        Returns the number of removed snapshot entries.
        """
        StateManager._ensure_dir()
        if not os.path.exists(HISTORY_FILE):
            return 0
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            history: List[Dict[str, Any]] = json.load(f)
        if not isinstance(history, list):
            return 0
        idx = next(
            (i for i, h in enumerate(history) if h.get("version") == branch_version),
            None,
        )
        if idx is None:
            logger.warning(
                "truncate_future_after_version: %r not in history; skipping",
                branch_version,
            )
            return 0
        tail = history[idx + 1 :]
        if not tail:
            return 0
        for h in tail:
            ver = h.get("version") or ""
            if not ver:
                continue
            v_dir = os.path.join(SNAPSHOT_DIR, ver)
            if os.path.isdir(v_dir):
                try:
                    shutil.rmtree(v_dir)
                except OSError as e:
                    logger.error("Could not remove snapshot dir %s: %s", v_dir, e)
        history = history[: idx + 1]
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
        logger.info(
            "Truncated %d snapshot(s) after branch %r",
            len(tail),
            branch_version,
        )
        return len(tail)

    @staticmethod
    def revert(version: str) -> Dict[str, Any]:
        """
        Restores state and assets from a previous snapshot.
        """
        StateManager._ensure_dir()
        v_dir = os.path.join(SNAPSHOT_DIR, version)
        state_file = os.path.join(v_dir, "state.json")
        asset_dir = os.path.join(v_dir, "assets")
        
        if not os.path.exists(state_file):
            raise FileNotFoundError(f"Snapshot {version} not found at {state_file}")
            
        # 1. Load state
        with open(state_file, "r") as f:
            state = json.load(f)
            
        # 2. Restore assets
        if os.path.exists(asset_dir):
            # To ensure a clean revert, we identify which directories we are about to restore to 
            # and we could potentially clear them. However, a safer approach is to just 
            # overwrite files. To be truly "proper", we should track exactly what was in the 
            # live folders. For now, we overwrite. 
            
            for root, _, files in os.walk(asset_dir):
                for f in files:
                    src = os.path.join(root, f)
                    rel = os.path.relpath(src, asset_dir)
                    dest = os.path.join(os.getcwd(), rel)
                    
                    # If the file exists in live, remove it first to avoid link/permission issues
                    if os.path.exists(dest):
                        try:
                            os.remove(dest)
                        except:
                            pass
                            
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(src, dest)
        
        logger.info(f"⏪ [StateManager] Reverted to {version}.")
        return state
