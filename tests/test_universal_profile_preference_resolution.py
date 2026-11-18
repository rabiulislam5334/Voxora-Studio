from __future__ import annotations

from app.universal.engines import EngineCapabilities, EngineDescriptor, EngineRegistry
from app.universal.profile_preference_resolution import (
    EnginePreferenceStatus,
    ProfilePreferenceResolver,
)
from app.universal.profiles.models import ChannelProfile


def descriptor(engine_id, *, available=True, scene_kinds=("image",), style_tags=("documentary",)):
    return EngineDescriptor(
        engine_id=engine_id,
        display_name=engine_id,
        version="1",
        capabilities=EngineCapabilities(
            scene_kinds=scene_kinds,
            style_tags=style_tags,
            asset_kinds=("image",),
            output_formats=("mp4",),
        ),
        available=available,
        unavailable_reason="dependency missing" if not available else "",
    )


def profile(preferred):
    return ChannelProfile.from_dict({
        "schema_version": 1,
        "profile_id": "test-channel",
        "display_name": "Test Channel",
        "preferred_engines": preferred,
    })


def make_registry():
    return EngineRegistry([
        descriptor("preferred-good"),
        descriptor("explicit-choice"),
        descriptor("offline", available=False),
        descriptor("wrong-kind", scene_kinds=("video",)),
    ])


def test_preferences_are_ordered_advisory_suggestions_only():
    registry = make_registry()
    before = registry.list_engines(include_unavailable=True)
    selected_id = "explicit-choice"

    result = ProfilePreferenceResolver(registry).resolve(
        profile(["preferred-good", "offline", "wrong-kind", "missing"]),
        selected_engine_id=selected_id,
        scene_kind="image",
        style_tags=("documentary",),
        asset_kinds=("image",),
        output_format="mp4",
    )

    assert result.selected_engine_id == selected_id
    assert result.selected_engine_resolution.status == "compatible"
    assert result.selected_engine_resolution.selected_descriptor.engine_id == selected_id
    assert [item.engine_id for item in result.preferences] == [
        "preferred-good", "offline", "wrong-kind", "missing"
    ]
    assert [item.status for item in result.preferences] == [
        EnginePreferenceStatus.COMPATIBLE,
        EnginePreferenceStatus.UNAVAILABLE,
        EnginePreferenceStatus.INCOMPATIBLE,
        EnginePreferenceStatus.UNKNOWN,
    ]
    assert [item.engine_id for item in result.compatible_preferred_engines] == [
        "preferred-good"
    ]
    assert result.requires_user_confirmation is True
    assert registry.list_engines(include_unavailable=True) == before


def test_profile_preference_does_not_replace_incompatible_explicit_selection():
    result = ProfilePreferenceResolver(make_registry()).resolve(
        profile(["preferred-good"]),
        selected_engine_id="wrong-kind",
        scene_kind="image",
    )

    assert result.selected_engine_id == "wrong-kind"
    assert result.selected_engine_resolution.status == "incompatible"
    assert result.selected_engine_resolution.selected_descriptor is None
    assert result.compatible_preferred_engines[0].engine_id == "preferred-good"
    assert result.requires_user_confirmation is True


def test_no_profile_preferences_does_not_invent_a_recommendation():
    result = ProfilePreferenceResolver(make_registry()).resolve(
        profile([]), selected_engine_id=None, scene_kind="image"
    )

    assert result.preferences == ()
    assert result.compatible_preferred_engines == ()
    assert result.selected_engine_resolution.status == "selection_required"
    assert result.requires_user_confirmation is False


def test_future_read_only_profile_preferences_are_not_interpreted():
    future = ChannelProfile.from_dict({
        "schema_version": 999,
        "profile_id": "future",
        "display_name": "Future",
        "preferred_engines": ["preferred-good"],
    })

    result = ProfilePreferenceResolver(make_registry()).resolve(
        future, selected_engine_id="explicit-choice"
    )

    assert result.supported is False
    assert result.preferences == ()
    assert result.selected_engine_resolution is None
    assert result.requires_user_confirmation is False
