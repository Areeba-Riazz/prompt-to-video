"""Unit tests for story-aware BGM planning (no network)."""

from shared.bgm_plan import plan_bgm


def test_skip_when_no_bgm_requested():
    jobs = [
        {
            "scene": {
                "location": "Studio",
                "dialogue": [
                    {"line": "This is a silent film style piece — no background music please."}
                ],
            }
        }
    ]
    p = plan_bgm(jobs)
    assert p["apply_bgm"] is False
    assert "no_bgm" in p["reason"]


def test_funeral_biases_sad_and_quieter():
    jobs = [
        {
            "scene": {
                "location": "Funeral parlor",
                "dialogue": [{"line": "We will miss him every day.", "emotion": "sad"}],
            }
        }
    ]
    p = plan_bgm(jobs)
    assert p["apply_bgm"] is True
    assert p["mood"] == "sad"
    assert p["volume_multiplier"] < 1.0
    assert "funeral" in (p.get("freesound_boost") or "").lower() or "melancholic" in p.get("freesound_boost", "")


def test_chase_biases_tense():
    jobs = [
        {
            "scene": {
                "location": "Alley at night",
                "dialogue": [{"line": "They're chasing us — run!", "emotion": "fear"}],
            }
        }
    ]
    p = plan_bgm(jobs)
    assert p["apply_bgm"] is True
    assert p["mood"] == "tense"


def test_user_prompt_influences_skip():
    jobs = [{"scene": {"dialogue": [{"line": "Hello there."}]}}]
    p = plan_bgm(jobs, user_prompt="Documentary interview, dialogue only.")
    assert p["apply_bgm"] is False
