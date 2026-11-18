from __future__ import annotations

import copy

import pytest

from app.universal.profiles import (
    ChannelProfile,
    ProductionDefaults,
    ProductionPreset,
    ProductionRule,
    ProfileValidationError,
    VisualDefaults,
)


def sample_profile() -> ChannelProfile:
    review = ProductionRule(
        rule_id="verify-sources",
        category="review",
        severity="warning",
        scope="project",
        target="sources",
        operator="manual_review",
        message="Review factual sources before approval.",
    )
    preset = ProductionPreset(
        preset_id="islamic-2d-storytelling",
        display_name="Islamic 2D Cartoon Storytelling",
        visual_defaults=VisualDefaults(
            style_family="2d_cartoon",
            style_tags=("consistent_characters", "narration_synced"),
        ),
        rules=(review,),
    )
    return ChannelProfile(
        profile_id="rihvaya",
        display_name="Rihvaya",
        content_domains=("islamic_history", "quran_education"),
        audience={"language": "en", "region": "international"},
        visual_defaults=VisualDefaults(style_family="documentary_illustration"),
        production_defaults=ProductionDefaults(aspect_ratio="16:9", frame_rate=30),
        preferred_engines=("motion_graphics", "2d_cartoon"),
        rules=(review,),
        presets=(preset,),
    )


def test_profile_round_trip_preserves_nested_unknown_fields():
    raw = sample_profile().to_dict()
    raw["future_profile_setting"] = {"keep": [1, 2]}
    raw["visual_defaults"]["future_visual_field"] = "preserve"
    raw["presets"][0]["future_preset_field"] = True
    raw["rules"][0]["future_rule_field"] = {"retain": True}
    raw["presets"][0]["rules"][0]["future_rule_field"] = {"retain": True}

    loaded = ChannelProfile.from_dict(raw)

    assert loaded.to_dict() == raw
    assert loaded.presets[0].rules[0].extra["future_rule_field"] == {"retain": True}


def test_profile_does_not_mutate_input_or_share_nested_metadata():
    raw = sample_profile().to_dict()
    raw["metadata"] = {"nested": {"values": [1]}}
    before = copy.deepcopy(raw)

    loaded = ChannelProfile.from_dict(raw)
    exported = loaded.to_dict()
    exported["metadata"]["nested"]["values"].append(2)

    assert raw == before
    assert loaded.metadata == {"nested": {"values": [1]}}


def test_future_profile_schema_is_read_only_and_preserved_verbatim():
    raw = {
        "schema_version": 99,
        "profile_id": "Future/Profile-ID",
        "display_name": {"localized": ["Future profile"]},
        "new_contract": {"x": [1, 2]},
    }
    loaded = ChannelProfile.from_dict(raw)

    assert loaded.read_only
    assert loaded.to_dict() == raw


def test_invalid_profile_identifier_is_rejected():
    with pytest.raises(ProfileValidationError, match="stable lowercase identifier"):
        ChannelProfile(profile_id="Rihvaya Channel", display_name="Rihvaya")


def test_duplicate_rule_ids_are_rejected():
    rule = ProductionRule(
        rule_id="same-rule",
        category="recommended",
        severity="warning",
        scope="scene",
        target="visual_prompt",
        operator="exists",
        message="Add a visual prompt.",
    )
    with pytest.raises(ProfileValidationError, match="rule IDs must be unique"):
        ChannelProfile(profile_id="test", display_name="Test", rules=(rule, rule))


def test_review_rule_requires_manual_review_operator():
    with pytest.raises(ProfileValidationError, match="manual_review operator"):
        ProductionRule(
            rule_id="review-rule",
            category="review",
            severity="warning",
            scope="project",
            target="sources",
            operator="exists",
            message="Review sources.",
        )


def test_rule_rejects_non_json_executable_values():
    with pytest.raises(ProfileValidationError, match="JSON-compatible"):
        ProductionRule(
            rule_id="bad-rule",
            category="recommended",
            severity="warning",
            scope="scene",
            target="visual_prompt",
            operator="equals",
            expected=object(),
            message="Must remain data only.",
        )


def test_non_finite_values_are_rejected():
    with pytest.raises(ProfileValidationError, match="NaN or infinity"):
        ChannelProfile(
            profile_id="test",
            display_name="Test",
            metadata={"invalid": float("nan")},
        )


def test_production_defaults_validate_frame_rate():
    with pytest.raises(ProfileValidationError, match="frame_rate"):
        ProductionDefaults(frame_rate=0)


def test_preset_round_trip_keeps_rule_and_visual_defaults():
    profile = sample_profile()
    loaded = ChannelProfile.from_dict(profile.to_dict())

    assert loaded.presets[0].preset_id == "islamic-2d-storytelling"
    assert loaded.presets[0].visual_defaults.style_family == "2d_cartoon"
    assert loaded.presets[0].rules[0].operator == "manual_review"


def test_profile_schema_version_must_be_positive_integer():
    with pytest.raises(ProfileValidationError, match="positive integer"):
        ChannelProfile.from_dict({"schema_version": True})


def test_mutable_inputs_are_defensively_copied():
    metadata = {"nested": [1]}
    profile = ChannelProfile(profile_id="test", display_name="Test", metadata=metadata)
    metadata["nested"].append(2)

    assert profile.metadata == {"nested": [1]}
