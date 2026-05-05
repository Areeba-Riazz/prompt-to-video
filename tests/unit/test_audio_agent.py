import pytest
import os
import wave
from agents.audio_agent.agent import _parse_line_with_sfx, _wav_duration, _infer_emotion

def test_parse_line_with_sfx():
    """Test splitting dialogue into speech and SFX segments."""
    # Test case 1: Speech then SFX
    text1 = "Hello world (laughter)"
    segs1 = _parse_line_with_sfx(text1)
    assert len(segs1) == 2
    assert segs1[0] == {"type": "speech", "val": "Hello world"}
    assert segs1[1] == {"type": "sfx", "val": "laughter"}

    # Test case 2: SFX then Speech
    text2 = "[groans] This is hard."
    segs2 = _parse_line_with_sfx(text2)
    assert len(segs2) == 2
    assert segs2[0] == {"type": "sfx", "val": "groans"}
    assert segs2[1] == {"type": "speech", "val": "This is hard."}

    # Test case 3: Interleaved
    text3 = "Wait (sigh) okay."
    segs3 = _parse_line_with_sfx(text3)
    assert len(segs3) == 3
    assert segs3[0] == {"type": "speech", "val": "Wait"}
    assert segs3[1] == {"type": "sfx", "val": "sigh"}
    assert segs3[2] == {"type": "speech", "val": "okay."}

def test_infer_emotion():
    """Test emotion inference from text and visual cues."""
    assert _infer_emotion("I am so happy!", "") == "happy"
    assert _infer_emotion("I'm going to kill you.", "") == "angry"
    assert _infer_emotion("I'm so sorry for your loss.", "") == "sad"
    assert _infer_emotion("Please don't hurt me!", "") == "fearful"
    assert _infer_emotion("The weather is nice.", "") == "neutral"
    assert _infer_emotion("...", "He snarls angrily") == "angry"

def test_wav_duration(tmp_path):
    """Test duration probing of a mock WAV file."""
    path = str(tmp_path / "test.wav")
    
    # Create a dummy 1-second WAV (16kHz, 16-bit mono)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00" * 32000)
    
    dur = _wav_duration(path)
    assert dur == pytest.approx(1.0)
