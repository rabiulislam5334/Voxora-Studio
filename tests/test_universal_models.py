from __future__ import annotations

import copy

from app.universal.models import AssetRef, EngineChoice, ScenePlan, UniversalState


def test_universal_state_round_trip_preserves_unknown_nested_fields():
    raw = {
        "format_version": 1,
        "profile_id": "quasivanta",
        "future_project_field": {"keep": True},
        "scene_plans": {
            "scene-1": {
                "scene_id": "scene-1",
                "kind": "scientific_3d",
                "style_tags": ["cinematic", "sketch_overlay"],
                "requirements": {"needs_gpu": False, "custom_requirement": [1, 2]},
                "engine_choice": {
                    "engine_id": "threejs",
                    "fallback_chain": ["hyperframes", "ffmpeg"],
                    "reason": "3D scientific subject",
                    "chosen_by": "director",
                    "future_engine_flag": "preserve-me",
                },
                "camera": {"movement": "orbit"},
                "asset_refs": [{
                    "asset_id": "earth-texture",
                    "kind": "texture",
                    "path": "assets/earth.jpg",
                    "identity": "sha256:abc",
                    "license": "CC-BY-4.0",
                    "metadata": {"width": 4096},
                    "future_asset_field": 42,
                }],
                "complexity_estimate": 0.7,
                "notes": "Test plan",
                "plan_status": "proposed",
                "script_hash": "script-v1",
                "future_scene_field": {"retain": "yes"},
            }
        },
    }
    state = UniversalState.from_dict(raw)
    assert not state.read_only
    assert state.to_dict() == raw


def test_future_universal_format_is_read_only_and_preserved_verbatim():
    raw = {"format_version": 99, "new_payload": {"x": [1, 2, 3]}}
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw
    assert state.apply_to_project_settings({"studio": {"keep": True}}) == {"studio": {"keep": True}}


def test_malformed_universal_payload_is_read_only_and_preserved():
    raw = {"format_version": 1, "scene_plans": {"scene-1": {"scene_id": "wrong-id"}}}
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw


def test_non_object_universal_payload_is_preserved_read_only():
    raw = ["future", "format"]
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw


def test_scene_plan_duplicate_is_deep_copied_and_resets_approval():
    state = UniversalState(scene_plans={
        "source": ScenePlan(
            scene_id="source",
            kind="map_animation",
            requirements={"layers": ["roads"]},
            engine_choice=EngineChoice(engine_id="maplibre"),
            asset_refs=[AssetRef(asset_id="map", kind="vector", metadata={"zoom": 5})],
            plan_status="approved",
        )
    })
    cloned = state.duplicate_scene_plan("source", "copy")
    assert cloned is not None
    assert cloned.scene_id == "copy"
    assert cloned.plan_status == "draft"
    cloned.requirements["layers"].append("borders")
    cloned.asset_refs[0].metadata["zoom"] = 8
    assert state.scene_plans["source"].requirements == {"layers": ["roads"]}
    assert state.scene_plans["source"].asset_refs[0].metadata == {"zoom": 5}


def test_prune_scenes_removes_only_deleted_scene_plans():
    state = UniversalState(scene_plans={
        "keep": ScenePlan(scene_id="keep"),
        "delete": ScenePlan(scene_id="delete"),
    })
    state.prune_scenes(["keep"])
    assert list(state.scene_plans) == ["keep"]


def test_read_only_state_cannot_be_pruned_or_duplicated():
    raw = {"format_version": 2, "scene_plans": {}}
    state = UniversalState.from_dict(raw)
    state.prune_scenes([])
    assert state.duplicate_scene_plan("a", "b") is None
    assert state.to_dict() == raw


def test_apply_to_project_settings_does_not_mutate_input_or_studio_namespace():
    settings = {"studio": {"volume": 70}, "other": {"x": 1}}
    before = copy.deepcopy(settings)
    state = UniversalState(profile_id="veltracis")
    updated = state.apply_to_project_settings(settings)
    assert settings == before
    assert updated["studio"] == settings["studio"]
    assert updated["universal"]["profile_id"] == "veltracis"


def test_scene_plan_rejects_scene_id_key_mismatch():
    raw = {"format_version": 1, "scene_plans": {"scene-a": {"scene_id": "scene-b"}}}
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw


def test_non_finite_complexity_makes_universal_payload_read_only():
    for complexity in (float("nan"), float("inf"), float("-inf")):
        raw = {
            "format_version": 1,
            "scene_plans": {
                "scene-1": {
                    "scene_id": "scene-1",
                    "complexity_estimate": complexity,
                }
            },
        }
        state = UniversalState.from_dict(raw)
        assert state.read_only
        assert state.to_dict() == raw


def test_overflowing_complexity_makes_universal_payload_read_only():
    raw = {
        "format_version": 1,
        "scene_plans": {
            "scene-1": {
                "scene_id": "scene-1",
                "complexity_estimate": 10 ** 10000,
            }
        },
    }
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw


def test_unknown_plan_status_makes_universal_payload_read_only():
    raw = {
        "format_version": 1,
        "scene_plans": {
            "scene-1": {
                "scene_id": "scene-1",
                "plan_status": "approvd",
            }
        },
    }
    state = UniversalState.from_dict(raw)
    assert state.read_only
    assert state.to_dict() == raw

