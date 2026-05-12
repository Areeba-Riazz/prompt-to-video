from typing import Any, Dict, List
import json
import os
from mcp.base_tool import BaseTool
from state_manager.memory_manager import memory_manager
from shared.repo_paths import resolve_from_repo as _resolve_repo


def _phase1_dir() -> str:
    return _resolve_repo(os.environ.get("PHASE1_OUTPUT_DIR", "data/outputs/phase1"))

class MemoryCommitTool(BaseTool):
    @property
    def name(self) -> str:
        return "commit_memory"

    @property
    def description(self) -> str:
        return "Commits character or script metadata to the persistent memory layer."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "key": "str — The key under which to store the memory (e.g. char_name)",
            "data": "Dict[str, Any] — The metadata to store",
        }

    @property
    def tags(self) -> list[str]:
        return ["system", "state", "memory"]

    def execute(self, **kwargs) -> Any:
        key = kwargs.get("key", "")
        data = kwargs.get("data", {})
        
        try:
            if key.startswith("char_"):
                description = data.get("appearance", "Character entry")
                traits = {
                    "name": data.get("name"),
                    "personality": data.get("personality"),
                    "appearance": data.get("appearance"),
                    "voice_profile": data.get("voice_profile"),
                    "reference_style": data.get("reference_style"),
                    "image_path": data.get("image_path"),
                    "gender": data.get("gender"),
                    "edge_voice": data.get("edge_voice"),
                    "tts_voice": data.get("tts_voice"),
                    "kokoro_voice": data.get("kokoro_voice"),
                }
                memory_manager.store_character(
                    character_name=key.replace("char_", ""),
                    description=data.get("appearance", "Character entry"),
                    traits=traits,
                )
                
                # Write to character_db.json
                phase1_dir = _phase1_dir()
                db_path = os.path.join(phase1_dir, "character_db.json")
                os.makedirs(phase1_dir, exist_ok=True)
                
                chars = []
                if os.path.exists(db_path):
                    try:
                        with open(db_path, "r") as f:
                            chars = json.load(f)
                            if isinstance(chars, dict) and "characters" in chars:
                                chars = chars["characters"]
                    except: chars = []
                
                # Update or add
                existing = next((c for c in chars if c.get("name") == data.get("name")), None)
                if existing:
                    existing.update(traits)
                else:
                    chars.append(traits)
                
                with open(db_path, "w") as f:
                    json.dump({"characters": chars}, f, indent=4)

            elif key == "final_manifest":
                # Write to scene_manifest.json
                phase1_dir = _phase1_dir()
                manifest_path = os.path.join(phase1_dir, "scene_manifest.json")
                os.makedirs(phase1_dir, exist_ok=True)
                
                # data is expected to be a list of scenes
                scenes = []
                if isinstance(data, list):
                    scenes = [s.dict() if hasattr(s, "dict") else s for s in data]
                
                with open(manifest_path, "w") as f:
                    json.dump({"scenes": scenes}, f, indent=4)
                    
                memory_manager.store_script(
                    script_id=key, content=json.dumps(scenes), metadata={"source": "workflow"}
                )
            else:
                memory_manager.store_script(
                    script_id=key, content=str(data), metadata={"source": "workflow"}
                )
            return {"ok": True, "key": key}
        except Exception as exc:
            return {"ok": False, "key": key, "error": str(exc)}

class TaskGraphTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_task_graph"

    @property
    def description(self) -> str:
        return "Decomposes scene_manifest.json into parallelizable scene tasks."

    @property
    def input_schema(self) -> Dict[str, str]:
        return {
            "scenes": "List[Dict] — List of scenes to decompose. Used for legacy Phase 1",
            "manifest_path": "str — path to scene_manifest.json. Used for Phase 2",
            "parallel": "bool — whether to enable parallel branching (default True)",
        }

    @property
    def tags(self) -> list[str]:
        return ["system", "planning", "state"]

    def execute(self, **kwargs) -> Any:
        # Support both Phase 1 (scenes directly) and Phase 2 (manifest path)
        if "scenes" in kwargs:
            scenes = kwargs["scenes"]
            graph = []
            for scene in scenes:
                sid = int(scene.get("scene_id", 0))
                graph.append({
                    "task_id": f"task_scene_{sid:02d}",
                    "scene_id": sid,
                    "stages": ["voice", "video", "face_swap", "lip_sync"],
                    "parallelizable": True,
                })
            return graph
            
        elif "manifest_path" in kwargs:
            # We'll pull the logic from tools/task_graph.py directly here
            manifest_path = kwargs.get("manifest_path")
            parallel = kwargs.get("parallel", True)
            
            import json
            import os
            if not manifest_path or not os.path.exists(manifest_path):
                return []
                
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
                
            tasks = []
            for scene in manifest.get("scenes", []):
                sid = scene.get("scene_id", 0)
                tasks.append({
                    "task_id": f"scene_{sid}",
                    "scene_id": sid,
                    "stages": ["voice", "video", "face_swap", "lip_sync"],
                    "parallelizable": parallel,
                    **scene # Include all scene data (location, characters, dialogue, etc.)
                })
            return {"tasks": tasks, "parallel_enabled": parallel}
        
        return {"tasks": [], "parallel_enabled": False}
