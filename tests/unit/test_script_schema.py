import pytest
import json
from agents.story_agent.agent import ScriptwriterAgent
from shared.schemas.state import MontageState, Scene

def test_script_parsing():
    """Test that the ScriptwriterAgent correctly parses a valid JSON payload into Scene objects."""
    agent = ScriptwriterAgent()
    
    valid_payload = {
        "scenes": [
            {
                "scene_id": 1,
                "location": "INT. CAFE - DAY",
                "characters": ["Alex", "Sora"],
                "dialogue": [
                    {
                        "speaker": "Alex",
                        "line": "Hello there.",
                        "visual_cue": "Alex waves cheerfully."
                    }
                ]
            }
        ]
    }
    
    raw_text = json.dumps(valid_payload)
    scenes = agent._parse_scene_payload(raw_text)
    
    assert scenes is not None
    assert len(scenes) == 1
    assert isinstance(scenes[0], Scene)
    assert scenes[0].scene_id == 1
    assert scenes[0].location == "INT. CAFE - DAY"
    assert "Alex" in scenes[0].characters
    assert scenes[0].dialogue[0]["speaker"] == "Alex"

def test_script_parsing_with_markdown():
    """Test that the parser can handle markdown-wrapped JSON."""
    agent = ScriptwriterAgent()
    
    markdown_payload = """
    Here is the script:
    ```json
    {
      "scenes": [
        {
          "scene_id": 2,
          "location": "EXT. PARK - NIGHT",
          "characters": ["Kael"],
          "dialogue": [{"speaker": "Kael", "line": "Quiet tonight.", "visual_cue": "Kael looks at stars."}]
        }
      ]
    }
    ```
    """
    
    scenes = agent._parse_scene_payload(markdown_payload)
    assert scenes is not None
    assert len(scenes) == 1
    assert scenes[0].scene_id == 2

def test_script_parsing_failure():
    """Test that the parser returns None for invalid JSON."""
    agent = ScriptwriterAgent()
    invalid_text = "This is not JSON at all."
    scenes = agent._parse_scene_payload(invalid_text)
    assert scenes is None
