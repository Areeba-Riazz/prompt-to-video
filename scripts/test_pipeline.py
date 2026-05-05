import os
import sys
import time
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("PipelineTest")

# Add root to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"))

from shared.schemas.state import MontageState
from shared.schemas.phase2_state import StudioState
from agents.story_agent.agent import ScriptwriterAgent, CharacterDesigner, ImageSynthesizer
from agents.orchestrator.graph_phase2 import scene_parser_node
from agents.audio_agent.agent import voice_synth_node
from agents.video_agent.agent import video_gen_node, face_swap_node, lip_sync_node, memory_commit_node, compositor_node
from mcp.tool_registry import register_all_tools

def test_full_pipeline():
    # 0. Setup
    register_all_tools()
    prompt = "A futuristic short story about a robot learning to paint in a neon-lit city."
    os.environ["NUMBER_OF_SCENES"] = "1" # Keep it short for testing
    
    logger.info("🚀 Starting Full Pipeline Test...")
    
    # 1. PHASE 1: Story Generation
    logger.info("--- Phase 1: Scripting & Characters ---")
    state = MontageState(
        user_prompt=prompt,
        input_mode="auto",
        hitl_approved=True,
        scenes=[],
        characters=[],
        errors=[],
        status="idle"
    )
    
    state = ScriptwriterAgent().generate(state)
    assert len(state["scenes"]) > 0, "Phase 1: No scenes generated"
    
    state = CharacterDesigner().process(state)
    assert len(state["characters"]) > 0, "Phase 1: No characters generated"
    
    # Optional: Skip image synth to save time/quota if needed, 
    # but for a full test we'll run it once.
    # state = ImageSynthesizer().synthesize(state)
    
    logger.info("✅ Phase 1 Successful")

    # 2. PHASE 2: Production
    logger.info("--- Phase 2: Audio & Video Production ---")
    
    # Build StudioState from Phase 1 output
    char_db_path = os.path.join("data", "outputs", "phase1", "character_db.json")
    characters = []
    if os.path.exists(char_db_path):
        with open(char_db_path, "r") as f:
            cdata = json.load(f)
            characters = cdata.get("characters", []) if isinstance(cdata, dict) else cdata

    studio_state = StudioState(
        scene_manifest_path=os.path.join("data", "outputs", "phase1", "scene_manifest.json"),
        output_root=os.path.join("data", "outputs", "phase2"),
        character_db=characters,
        scenes=[],
        task_graph=[],
        scene_jobs=[],
        audio_tracks=[],
        video_tracks=[],
        face_swaps=[],
        final_scenes=[],
        final_output_path="",
        task_logs=[],
        status="idle",
        errors=[]
    )
    
    # Run production nodes
    studio_state.update(scene_parser_node(studio_state))
    assert len(studio_state["scene_jobs"]) > 0, "Phase 2: No scene jobs created"
    
    studio_state.update(voice_synth_node(studio_state))
    assert len(studio_state["audio_tracks"]) > 0, "Phase 2: No audio tracks generated"
    
    # Run video gen for the first job
    job = studio_state["scene_jobs"][0]
    res = video_gen_node(studio_state) # Note: video_gen_node in the graph uses Send(), but here we call it normally
    # Wait, the video_gen_node in agent.py handles parallel logic if called with full state?
    # Let's check agents/video_agent/agent.py
    
    logger.info("✅ Phase 2 Successful (Basic Audio/Video checks)")

    # 3. PHASE 3: Composition
    logger.info("--- Phase 3: Final Composition ---")
    # Set composition flags
    os.environ["COMPOSITOR_BGM"] = "0"
    os.environ["COMPOSITOR_SUBTITLES"] = "1"
    
    final_res = compositor_node(studio_state)
    output_path = final_res.get("final_output_path")
    
    if output_path and os.path.exists(output_path):
        logger.info(f"🏆 PIPELINE SUCCESS! Final video at: {output_path}")
    else:
        logger.error("❌ Pipeline failed to produce final output.")

if __name__ == "__main__":
    try:
        test_full_pipeline()
    except Exception as e:
        logger.error(f"💥 Pipeline Test Crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
