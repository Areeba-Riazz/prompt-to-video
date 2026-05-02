from typing import Annotated, Any, Dict, List, TypedDict
import operator


class StudioState(TypedDict):
    # Input
    scene_manifest_path: str
    output_root: str

    # Phase 1 data passed in at startup
    character_db: List[Dict[str, Any]]  # list of character dicts from character_db.json
    scene_id_filter: int

    # Parsed/Planning
    scenes: List[Dict[str, Any]]
    task_graph: List[Dict[str, Any]]
    scene_jobs: List[Dict[str, Any]]

    # Intermediate + final outputs (merged across parallel branches)
    audio_tracks: Annotated[List[Dict[str, Any]], operator.add]
    video_tracks: Annotated[List[Dict[str, Any]], operator.add]
    face_swaps: Annotated[List[Dict[str, Any]], operator.add]
    final_scenes: Annotated[List[Dict[str, Any]], operator.add]
    task_logs: Annotated[List[Dict[str, Any]], operator.add]

    # Control
    status: str
    errors: Annotated[List[str], operator.add]
    current_agent: str
