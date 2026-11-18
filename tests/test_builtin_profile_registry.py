from __future__ import annotations

from app.universal.profiles import (
    BUILTIN_PROFILE_REGISTRY,
    BuiltinProfileRegistry,
    ChannelProfile,
    ProfileValidationError,
    get_builtin_profile,
    list_builtin_profiles,
)


EXPECTED_PROFILE_IDS = (
    "quasivanta",
    "veltracis",
    "sizzjin",
    "drowsehaven",
    "rihvaya",
    "mindniq",
    "inventions-discoveries",
)


def test_builtin_registry_has_all_profiles_in_deterministic_order():
    assert BUILTIN_PROFILE_REGISTRY.profile_ids == EXPECTED_PROFILE_IDS
    assert tuple(profile.profile_id for profile in list_builtin_profiles()) == EXPECTED_PROFILE_IDS
    assert tuple(profile.profile_id for profile in list_builtin_profiles()) == EXPECTED_PROFILE_IDS


def test_registry_lookup_returns_profile_or_none():
    profile = get_builtin_profile("quasivanta")

    assert isinstance(profile, ChannelProfile)
    assert profile.display_name == "Quasivanta"
    assert get_builtin_profile("not-a-real-channel") is None
    assert get_builtin_profile(None) is None


def test_rihvaya_has_the_two_documented_production_presets():
    profile = get_builtin_profile("rihvaya")

    assert profile is not None
    assert tuple(preset.preset_id for preset in profile.presets) == (
        "islamic_documentary",
        "islamic_2d_cartoon_storytelling",
    )
    cartoon = profile.presets[1]
    assert cartoon.visual_defaults.style_family == "2d_cartoon_storytelling"
    assert "narration_synced_actions" in cartoon.visual_defaults.style_tags


def test_every_builtin_profile_validates_and_round_trips():
    for profile in list_builtin_profiles():
        assert not profile.read_only
        restored = ChannelProfile.from_dict(profile.to_dict())
        assert restored.to_dict() == profile.to_dict()


def test_registry_returns_fresh_instances_and_defensive_nested_data():
    first = get_builtin_profile("rihvaya")
    first.audience["language"] = "mutated"
    first.metadata["nested"] = {"values": [1]}
    first.metadata["nested"]["values"].append(2)

    second = get_builtin_profile("rihvaya")

    assert second is not first
    assert second.audience["language"] == "en"
    assert "nested" not in second.metadata


def test_registry_constructor_rejects_duplicate_profile_ids():
    document = get_builtin_profile("quasivanta").to_dict()

    try:
        BuiltinProfileRegistry((document, document))
    except ProfileValidationError as exc:
        assert "duplicate built-in profile ID" in str(exc)
    else:
        raise AssertionError("duplicate profile IDs must be rejected")
