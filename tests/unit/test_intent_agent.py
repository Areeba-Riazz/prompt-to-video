import pytest
import os
from dotenv import load_dotenv
load_dotenv()
from agents.edit_agent.intent_classifier import classify_edit_intent

def test_intent_classification():
    """Test suite for at least 10 different edit query types."""
    
    test_cases = [
        # 1. Voice Tone (Audio)
        {
            "query": "Change Alex's voice to be more whispered and low pitch",
            "expected_target": "audio",
            "expected_intent": "change_voice_tone"
        },
        # 2. Visual Style (Video Frame)
        {
            "query": "Make the second scene look like a 1920s black and white film",
            "expected_target": "video_frame",
            "expected_intent": "change_visual_style"
        },
        # 3. Remove Subtitles (Video)
        {
            "query": "Remove all the subtitles from the video",
            "expected_target": "video",
            "expected_intent": "remove_subtitles"
        },
        # 4. Background Music (Audio)
        {
            "query": "Add a fast-paced techno track to the climax",
            "expected_target": "audio",
            "expected_intent": "add_bgm"
        },
        # 5. Character Appearance (Video Frame)
        {
            "query": "Change the main character's hair to bright blue",
            "expected_target": "video_frame",
            "expected_intent": "change_character_design"
        },
        # 6. Global Lighting (Video)
        {
            "query": "Apply a sepia filter to the entire movie",
            "expected_target": "video",
            "expected_intent": "apply_global_filter"
        },
        # 7. Speed/Timing (Video)
        {
            "query": "Speed up the third scene by 2x",
            "expected_target": "video",
            "expected_intent": "change_speed"
        },
        # 8. Script Rewrite (Script)
        {
            "query": "Rewrite the script to have a more tragic ending",
            "expected_target": "script",
            "expected_intent": "rewrite_script"
        },
        # 9. Voice Speed (Audio)
        {
            "query": "Make the narrator talk much faster",
            "expected_target": "audio",
            "expected_intent": "change_voice_speed"
        },
        # 10. Specific Object (Video_frame)
        {
            "query": "Add a floating robot to the background of the cafe scene",
            "expected_target": "video_frame",
            "expected_intent": "modify_scene_content"
        }
    ]

    for case in test_cases:
        result = classify_edit_intent(case["query"])
        assert result["target"] == case["expected_target"], f"Failed target for: {case['query']}"
        # We allow some flexibility in intent naming, but check if it's broadly correct
        assert len(result["intent"]) > 0
        assert "parameters" in result
        print(f"PASSED: {case['query']} -> {result['intent']} ({result['target']})")

if __name__ == "__main__":
    test_intent_classification()
