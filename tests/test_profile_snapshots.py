from __future__ import annotations

import copy

import pytest

from app.universal.models import UniversalState
from app.universal.profiles import ProfileSnapshot, get_builtin_profile


def test_profile_snapshot_round_trips_builtin_profile_and_preset():
    profile = get_builtin_profile("rihvaya")
    assert profile is not None
    preset_id = next(p.preset_id for p in profile.presets if p.preset_id == "islamic_documentary")
    snapshot = ProfileSnapshot.from_profile(profile, selected_preset_id=preset_id)
    restored = ProfileSnapshot.from_dict(snapshot.to_dict())
    assert restored.profile_id == "rihvaya"
    assert restored.selected_preset_id == "islamic_documentary"
    assert restored.to_dict() == snapshot.to_dict()


def test_universal_state_persists_profile_snapshot_without_rewriting_scenes():
    profile = get_builtin_profile("quasivanta")
    state = UniversalState()
    state.set_profile_snapshot(profile)
    state.scene_plans = {}
    raw = state.to_dict()
    restored = UniversalState.from_dict(raw)
    assert not restored.read_only
    assert restored.profile_id == "quasivanta"
    assert restored.profile_snapshot is not None
    assert restored.profile_snapshot.profile_id == "quasivanta"
    assert restored.to_dict() == raw


def test_profile_snapshot_is_project_local_and_defensively_copied():
    profile = get_builtin_profile("veltracis")
    snapshot = ProfileSnapshot.from_profile(profile)
    raw = snapshot.to_dict()
    raw["profile_data"]["audience"]["region"] = "mutated"
    assert snapshot.profile_data["audience"]["region"] == "international"


def test_snapshot_preserves_unknown_envelope_fields():
    profile = get_builtin_profile("sizzjin")
    raw = {
        "snapshot_version": 1,
        "profile_data": profile.to_dict(),
        "selected_preset_id": None,
        "future_snapshot_metadata": {"retain": True},
    }
    restored = ProfileSnapshot.from_dict(raw)
    assert restored.to_dict() == raw


def test_future_snapshot_version_makes_universal_state_read_only():
    raw = {
        "format_version": 1,
        "profile_id": "quasivanta",
        "scene_plans": {},
        "profile_snapshot": {"snapshot_version": 99, "new_field": {"preserve": True}},
    }
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw


def test_profile_snapshot_id_must_match_selected_profile_id():
    profile = get_builtin_profile("quasivanta")
    raw = {
        "format_version": 1,
        "profile_id": "veltracis",
        "scene_plans": {},
        "profile_snapshot": ProfileSnapshot.from_profile(profile).to_dict(),
    }
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw


def test_set_profile_snapshot_rejects_conflicting_selected_profile():
    state = UniversalState(profile_id="veltracis")
    with pytest.raises(ValueError, match="must match"):
        state.set_profile_snapshot(get_builtin_profile("quasivanta"))


def test_profile_snapshot_round_trip_keeps_unknown_profile_fields():
    profile = get_builtin_profile("mindniq")
    profile_data = profile.to_dict()
    profile_data["future_profile_setting"] = {"enabled": True}
    snapshot = ProfileSnapshot.from_dict({
        "snapshot_version": 1,
        "profile_data": profile_data,
        "selected_preset_id": None,
    })
    assert snapshot.to_dict()["profile_data"]["future_profile_setting"] == {"enabled": True}


def test_profile_snapshot_settings_round_trip_preserves_other_project_settings():
    profile = get_builtin_profile("inventions-discoveries")
    state = UniversalState()
    state.set_profile_snapshot(profile)
    settings = {"studio": {"volume": 65}, "other": {"keep": [1, 2]}}
    before = copy.deepcopy(settings)
    updated = state.apply_to_project_settings(settings)
    assert settings == before
    assert updated["studio"] == before["studio"]
    assert updated["other"] == before["other"]
    reopened = UniversalState.from_project_settings(updated)
    assert reopened.profile_snapshot.profile_id == "inventions-discoveries"
