from typing import Annotated, List, TypedDict, Optional
from pydantic import BaseModel, Field

class Scene(BaseModel):
    scene_id: int
    location: str
    characters: List[str]
    dialogue: List[dict] # {speaker: str, line: str, visual_cue: str}

class Character(BaseModel):
    name: str
    personality: str
    appearance: str
    reference_style: str
    image_path: Optional[str] = None

class MontageState(TypedDict):
    # Input
    user_prompt: str
    input_mode: str # 'manual' | 'auto'
    
    # Processed Data
    raw_script: str
    scenes: List[Scene]
    characters: List[Character]
    
    # Status & Control
    status: str # 'processing' | 'validated' | 'generating' | 'completed' | 'failed'
    errors: List[str]
    current_agent: str
    
    # Deliverables
    scene_manifest_path: str
    character_db_path: str
    image_assets_dir: str
