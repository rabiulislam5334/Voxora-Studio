"""Phase 0 regression tests for forward-compatible Studio settings."""
from __future__ import annotations

import copy

from app.models.project import Project
from app.models.scene import Scene
from app.studio.models import StudioState


def test_unknown_studio_keys_survive_every_nested_level():
    raw = {
        "version": 1,
        "future_studio": {"enabled": True},
        "audio": {
            "narration_volume_percent": 90,
            "future_audio": {"ducking_db": -12},
            "tracks": [{
                "id": "t1", "path": "music.mp3", "future_track": ["x", "y"]
            }],
        },
        "video": {
            "aspect": "16:9",
            "future_video": {"grade": "cinematic"},
            "scenes": {
                "s1": {"media_path": "a.png", "future_scene_video": {"depth": 2}},
                "future_only": {"future_flag": True},
            },
        },
    }
    result = StudioState.from_dict(copy.deepcopy(raw)).to_dict()
    assert result["future_studio"] == raw["future_studio"]
    assert result["audio"]["future_audio"] == raw["audio"]["future_audio"]
    assert result["audio"]["tracks"][0]["future_track"] == ["x", "y"]
    assert result["video"]["future_video"] == raw["video"]["future_video"]
    assert result["video"]["scenes"]["s1"]["future_scene_video"] == {"depth": 2}
    assert result["video"]["scenes"]["future_only"]["future_flag"] is True


def test_newer_studio_version_is_preserved_and_read_only():
    raw = {"version": 2, "audio": {}, "video": {}, "future": {"x": 1}}
    state = StudioState.from_dict(raw)
    assert state.read_only is True
    assert state.to_dict() == raw


def test_contextual_unknown_version_does_not_downgrade_on_serialization():
    raw = {"version": 7, "audio": {"future_audio": 1}, "video": {"future_video": 2}}
    state = StudioState.from_dict(raw)
    saved = state.to_dict()
    assert saved["version"] == 7
    assert saved["audio"]["future_audio"] == 1
    assert saved["video"]["future_video"] == 2


def test_non_object_studio_payload_is_preserved_read_only():
    for raw in (None, "future-format", ["not", "an", "object"], 42):
        state = StudioState.from_dict(raw)
        assert state.read_only is True
        assert state.to_dict() == raw


def test_malformed_audio_and_video_payloads_are_preserved():
    raw = {"version": 1, "audio": ["bad-audio"], "video": "bad-video"}
    state = StudioState.from_dict(raw)
    assert state.read_only is True
    assert state.to_dict() == raw


def test_malformed_track_entries_and_tracks_container_are_not_dropped():
    malformed_items = [{"volume_percent": 20}, None, "bad-track"]
    raw = {"version": 1, "audio": {"tracks": malformed_items}, "video": {}}
    state = StudioState.from_dict(raw)
    assert state.read_only is True
    assert state.to_dict()["audio"]["tracks"] == malformed_items

    raw_container = {"version": 1, "audio": {"tracks": {"unexpected": True}}, "video": {}}
    assert StudioState.from_dict(raw_container).to_dict()["audio"]["tracks"] == {"unexpected": True}


def test_malformed_scene_entries_and_scenes_container_are_not_dropped():
    raw_entries = {"s1": "bad-scene", "s2": ["bad-scene"]}
    raw = {"version": 1, "audio": {}, "video": {"scenes": raw_entries}}
    state_entries = StudioState.from_dict(raw)
    assert state_entries.read_only is True
    assert state_entries.to_dict()["video"]["scenes"] == raw_entries

    raw_container = {"version": 1, "audio": {}, "video": {"scenes": ["bad-scenes"]}}
    state = StudioState.from_dict(raw_container)
    assert state.read_only is True
    assert state.to_dict()["video"]["scenes"] == ["bad-scenes"]


def test_duplicate_scene_deep_copies_unknown_metadata():
    project = Project()
    original = project.add_scene(Scene(
        id="original", title="Source", extra={"future": {"items": [1, 2]}}
    ))
    duplicate = project.duplicate_scene(original.id)
    assert duplicate.id != original.id
    assert duplicate.extra == original.extra
    assert duplicate.extra is not original.extra
    duplicate.extra["future"]["items"].append(3)
    assert original.extra["future"]["items"] == [1, 2]


def test_known_values_win_over_extra_values():
    state = StudioState()
    state.extra = {"version": 99, "audio": "not-audio", "custom": True}
    state.video.extra = {"fps": 1}
    result = state.to_dict()
    assert result["version"] == 1
    assert isinstance(result["audio"], dict)
    assert result["video"]["fps"] == 30
    assert result["custom"] is True
