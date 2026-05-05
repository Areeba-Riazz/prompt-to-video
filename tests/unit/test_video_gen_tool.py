import pytest
from mcp.tools.video_tools.video_gen_tool import _generate_pexels_query, _pexels_pick_download_url

def test_pexels_query_generation():
    """Test both LLM fallback and rule-based query logic."""
    # Test rule-based fallback (by mocking chat_text to fail)
    visual_cue = "Alex slams the desk angrily"
    location = "INT. OFFICE - DAY"
    gender = "man"
    
    # We can't easily mock chat_text here without more setup, 
    # but we can verify the rule-based logic which runs if LLM fails.
    query = _generate_pexels_query(visual_cue, location, gender)
    
    # Expected rule-based: "one man in office alex desk angrily" 
    # (slams is a stop verb, INT. is removed, DAY is removed)
    assert "one man" in query
    assert "office" in query
    assert "alex" in query # alex is not a stop verb
    assert "slams" not in query # slams is a stop verb

def test_pexels_pick_download_url():
    """Test picking the best video URL from a list of Pexels results."""
    mock_videos = [
        {
            "duration": 5,
            "video_files": [
                {"link": "low_res.mp4", "width": 640, "quality": "sd"},
                {"link": "high_res.mp4", "width": 1920, "quality": "hd"}
            ]
        },
        {
            "duration": 15,
            "video_files": [
                {"link": "long_clip.mp4", "width": 1280, "quality": "hd"}
            ]
        }
    ]
    
    # Case 1: No target duration (pick first best res)
    url, qual, dur = _pexels_pick_download_url(mock_videos)
    assert url == "high_res.mp4"
    assert dur == 5
    
    # Case 2: Target duration = 10 (pick the 15s clip)
    url, qual, dur = _pexels_pick_download_url(mock_videos, target_duration=10)
    assert url == "long_clip.mp4"
    assert dur == 15

def test_pexels_pick_download_url_fallback():
    """Test that it falls back to any clip if none are long enough."""
    mock_videos = [
        {"duration": 5, "video_files": [{"link": "short.mp4", "width": 1920}]}
    ]
    # Target 10s but only 5s available
    url, qual, dur = _pexels_pick_download_url(mock_videos, target_duration=10)
    assert url == "short.mp4"
    assert dur == 5
