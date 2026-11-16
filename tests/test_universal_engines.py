from __future__ import annotations

import pytest

from app.universal.engines import (
    EngineCapabilities,
    EngineCompatibilityError,
    EngineDescriptor,
    EngineRegistry,
    EngineUnavailableError,
    UnknownEngineError,
)


def make_engine(engine_id="ffmpeg", **overrides):
    values = {
        "engine_id": engine_id,
        "display_name": engine_id.upper(),
        "version": "1.0",
        "capabilities": EngineCapabilities(
            scene_kinds=("image", "footage"),
            style_tags=("documentary", "parallax"),
            asset_kinds=("image", "video"),
            output_formats=("mp4",),
            supports_draft_render=True,
            max_concurrent_jobs=2,
            estimated_memory_mb=512,
        ),
    }
    values.update(overrides)
    return EngineDescriptor(**values)


def test_registry_registers_and_lists_engines_deterministically():
    registry = EngineRegistry([make_engine("remotion"), make_engine("ffmpeg")])
    assert [item.engine_id for item in registry.list_engines()] == ["ffmpeg", "remotion"]


def test_duplicate_registration_requires_explicit_replace():
    registry = EngineRegistry([make_engine()])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(make_engine())
    replacement = make_engine(version="2.0")
    registry.register(replacement, replace=True)
    assert registry.get("ffmpeg").version == "2.0"


def test_registry_rejects_non_descriptor_values():
    registry = EngineRegistry()
    with pytest.raises(TypeError):
        registry.register({"engine_id": "fake"})


def test_unknown_engine_is_reported_without_fallback():
    registry = EngineRegistry([make_engine()])
    with pytest.raises(UnknownEngineError, match="unknown engine"):
        registry.resolve("missing")


def test_unavailable_engine_is_hidden_by_default_and_can_be_inspected():
    unavailable = make_engine(
        "threejs", available=False, unavailable_reason="Node runtime not installed"
    )
    registry = EngineRegistry([make_engine(), unavailable])
    assert [item.engine_id for item in registry.list_engines()] == ["ffmpeg"]
    assert len(registry.list_engines(include_unavailable=True)) == 2
    with pytest.raises(EngineUnavailableError, match="Node runtime"):
        registry.resolve("threejs")


def test_compatibility_discovery_returns_all_matches_not_a_selected_engine():
    registry = EngineRegistry([
        make_engine("ffmpeg"),
        make_engine("hyperframes"),
        make_engine("threejs", capabilities=EngineCapabilities(
            scene_kinds=("scientific_3d",),
            style_tags=("cinematic",),
            asset_kinds=("texture",),
            output_formats=("mp4",),
        )),
    ])
    matches = registry.find_compatible(
        scene_kind="image",
        style_tags=("documentary",),
        asset_kinds=("image",),
        output_format="mp4",
    )
    assert [item.engine_id for item in matches] == ["ffmpeg", "hyperframes"]


def test_resolve_requires_every_requested_capability():
    registry = EngineRegistry([make_engine()])
    resolved = registry.resolve(
        "ffmpeg",
        scene_kind="image",
        style_tags=("documentary",),
        asset_kinds=("image",),
        output_format="mp4",
    )
    assert resolved.engine_id == "ffmpeg"
    with pytest.raises(EngineCompatibilityError):
        registry.resolve("ffmpeg", scene_kind="scientific_3d")


def test_empty_capability_lists_do_not_claim_support():
    registry = EngineRegistry([make_engine(
        capabilities=EngineCapabilities()
    )])
    assert registry.find_compatible(scene_kind="image") == ()


def test_unregister_returns_descriptor_and_unknown_unregister_fails():
    registry = EngineRegistry([make_engine()])
    removed = registry.unregister("ffmpeg")
    assert removed.engine_id == "ffmpeg"
    with pytest.raises(UnknownEngineError):
        registry.unregister("ffmpeg")


@pytest.mark.parametrize("kwargs", [
    {"scene_kinds": ("image", "image")},
    {"style_tags": ("",)},
    {"max_concurrent_jobs": 0},
    {"estimated_memory_mb": True},
])
def test_capabilities_validate_declared_values(kwargs):
    with pytest.raises(ValueError):
        EngineCapabilities(**kwargs)


@pytest.mark.parametrize("kwargs", [
    {"engine_id": ""},
    {"engine_id": "has whitespace"},
    {"display_name": ""},
    {"version": ""},
    {"available": "yes"},
    {"available": True, "unavailable_reason": "not installed"},
])
def test_engine_descriptor_validates_identity_and_availability(kwargs):
    values = {
        "engine_id": "test",
        "display_name": "Test",
        "version": "1",
        "capabilities": EngineCapabilities(),
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        EngineDescriptor(**values)



@pytest.mark.parametrize("kwargs", [
    {"style_tags": "documentary"},
    {"asset_kinds": "image"},
    {"scene_kind": ""},
    {"output_format": ""},
])
def test_compatibility_queries_reject_malformed_requirements(kwargs):
    registry = EngineRegistry([make_engine()])
    with pytest.raises(ValueError):
        registry.find_compatible(**kwargs)
