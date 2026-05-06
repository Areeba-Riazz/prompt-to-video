"""Unit tests for Phase 5 edit → Phase 1 / Phase 2 bridge (no LLM, no network)."""

import json
import os

from agents.edit_agent import edit_execution as ex


def test_coalesce_edit_state_uses_characters_alias():
    state = {"characters": [{"name": "A", "gender": "female"}]}
    out = ex.coalesce_edit_state(state)
    assert out["character_db"] == [{"name": "A", "gender": "female"}]


def test_pitch_param_to_edge_offset_hz():
    assert ex.pitch_param_to_edge_offset_hz(0.8) < 0
    assert ex.pitch_param_to_edge_offset_hz(1.2) > 0
    assert ex.pitch_param_to_edge_offset_hz(1.0) == 0


def test_scene_ids_for_character(tmp_path):
    manifest = {
        "scenes": [
            {
                "scene_id": 1,
                "dialogue": [{"speaker": "Comedian", "line": "Hi"}],
            },
            {
                "scene_id": 2,
                "dialogue": [{"speaker": "Narrator", "line": "Hi"}],
            },
            {
                "scene_id": 3,
                "dialogue": [{"speaker": "comedian", "line": "Again"}],
            },
        ]
    }
    p = tmp_path / "scene_manifest.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    sids = ex.scene_ids_for_character(str(p), "Comedian")
    assert sids == [1, 3]


def test_expand_post_proc_map_character_scopes(tmp_path):
    manifest = {
        "scenes": [
            {"scene_id": 1, "dialogue": [{"speaker": "Alex", "line": "x"}]},
            {"scene_id": 2, "dialogue": [{"speaker": "Bob", "line": "y"}]},
        ]
    }
    p = tmp_path / "scene_manifest.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    raw = {
        "character:Alex": {"pitch": 0.85, "target": "audio_fx"},
        "global": {"volume": 1.1, "target": "audio_fx"},
    }
    out = ex.expand_post_proc_map_character_scopes(raw, str(p))
    assert "character:Alex" not in out
    assert out["scene:1"]["pitch"] == 0.85
    assert out["global"]["volume"] == 1.1


def test_apply_audio_target_character_pitch():
    intent = {
        "scope": "character:comedian",
        "parameters": {"pitch": 0.82, "gender": "female"},
    }
    state = {
        "character_db": [
            {"name": "comedian", "gender": "male", "edge_voice": "en-US-GuyNeural"},
        ],
    }
    st, dc, ds = ex.apply_audio_target_to_state(intent, state)
    assert dc is True and ds is False
    row = st["character_db"][0]
    assert row["gender"] == "female"
    assert "edge_pitch_offset_hz" in row


def test_apply_video_frame_marks_changed():
    intent = {"scope": "scene:2", "parameters": {"lighting": "dim"}}
    state = {
        "scenes": [
            {"scene_id": 1, "dialogue": [{"speaker": "A", "line": "x", "visual_cue": "a"}]},
            {"scene_id": 2, "dialogue": [{"speaker": "A", "line": "y", "visual_cue": "b"}]},
        ],
    }
    st, changed = ex.apply_video_frame_to_state(intent, state)
    assert changed is True
    cue = st["scenes"][1]["dialogue"][0]["visual_cue"]
    assert "lighting" in cue and "dim" in cue


def test_persist_and_restore_roundtrip(tmp_path):
    os.environ["PHASE1_OUTPUT_DIR"] = str(tmp_path)
    try:
        ex.persist_character_db([{"name": "Z", "gender": "neutral"}])
        ex.persist_scene_manifest_scenes([{"scene_id": 1, "dialogue": []}])
        assert (tmp_path / "character_db.json").exists()
        assert (tmp_path / "scene_manifest.json").exists()
        st = {
            "character_db": [{"name": "Z", "gender": "male"}],
            "scenes": [{"scene_id": 1, "dialogue": [{"speaker": "Z", "line": "ok"}]}],
        }
        ex.restore_phase1_disk_from_state(st)
        with open(tmp_path / "character_db.json", encoding="utf-8") as f:
            db = json.load(f)
        assert db["characters"][0]["gender"] == "male"
    finally:
        os.environ.pop("PHASE1_OUTPUT_DIR", None)
