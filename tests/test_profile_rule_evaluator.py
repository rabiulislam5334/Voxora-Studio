from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.universal.profiles import (
    ChannelProfile,
    ProductionPreset,
    ProductionRule,
    get_builtin_profile,
)
from app.universal.profiles.evaluator import ProfileDiagnostic, evaluate_profile_rules


def rule(rule_id, *, category="required", severity="error", scope="project",
         target="title", operator="exists", expected=None, message=None):
    return ProductionRule(
        rule_id=rule_id, category=category, severity=severity, scope=scope,
        target=target, operator=operator, expected=expected,
        message=message or f"Check {rule_id}.",
    )


def profile_with(*rules, presets=()):
    return ChannelProfile(
        profile_id="test-profile", display_name="Test Profile",
        rules=tuple(rules), presets=tuple(presets),
    )


def test_required_rule_reports_missing_or_empty_target():
    profile = profile_with(rule("need-title", target="metadata.title"))
    results = evaluate_profile_rules(profile, project={"metadata": {"title": ""}})
    assert len(results) == 1
    assert results[0].code == "PROFILE_RULE_REQUIRED"
    assert results[0].severity == "error"
    assert results[0].rule_id == "need-title"


def test_required_rule_passes_for_present_target_and_zero_is_present():
    profile = profile_with(rule("need-count", target="count"))
    assert evaluate_profile_rules(profile, project={"count": 0}) == ()


def test_recommended_rule_uses_authored_severity_and_reports_mismatch():
    profile = profile_with(rule(
        "recommend-16-9", category="recommended", severity="warning",
        target="aspect_ratio", operator="equals", expected="16:9",
    ))
    results = evaluate_profile_rules(profile, project={"aspect_ratio": "9:16"})
    assert results[0].code == "PROFILE_RULE_RECOMMENDED"
    assert results[0].severity == "warning"


def test_prohibited_rule_reports_when_condition_matches():
    profile = profile_with(rule(
        "ban-watermark", category="prohibited", severity="error",
        target="watermark", operator="equals", expected=True,
    ))
    results = evaluate_profile_rules(profile, project={"watermark": True})
    assert results[0].code == "PROFILE_RULE_PROHIBITED"


@pytest.mark.parametrize(
    ("operator", "actual", "expected"),
    [
        ("exists", "yes", None),
        ("equals", "16:9", "16:9"),
        ("not_equals", "9:16", "16:9"),
        ("in", "en", ["en", "bn"]),
        ("not_in", "fr", ["en", "bn"]),
        ("contains", ["maps", "artifacts"], "maps"),
    ],
)
def test_supported_predicate_operators_pass(operator, actual, expected):
    profile = profile_with(rule("operator-check", operator=operator, expected=expected))
    assert evaluate_profile_rules(profile, project={"title": actual}) == ()


def test_manual_review_stays_pending_until_explicitly_completed():
    profile = profile_with(rule(
        "verify-sources", category="review", severity="warning",
        target="sources", operator="manual_review",
    ))
    pending = evaluate_profile_rules(profile, project={})
    completed = evaluate_profile_rules(profile, project={}, completed_reviews={"verify-sources"})
    assert pending[0].code == "PROFILE_RULE_REVIEW_REQUIRED"
    assert completed == ()


def test_scene_and_scene_plan_rules_return_stable_subject_ids():
    profile = profile_with(
        rule("scene-prompt", scope="scene", target="visual_prompt"),
        rule("plan-kind", scope="scene_plan", target="kind"),
    )
    results = evaluate_profile_rules(
        profile,
        scenes=[{"id": "scene-a", "visual_prompt": ""}, {"id": "scene-b", "visual_prompt": "A forest"}],
        scene_plans={"scene-a": {"kind": ""}, "scene-b": {"kind": "illustration"}},
    )
    assert [(item.rule_id, item.subject_id) for item in results] == [
        ("scene-prompt", "scene-a"), ("plan-kind", "scene-a"),
    ]


def test_dataclass_fields_are_supported_without_invoking_arbitrary_properties():
    @dataclass
    class SafeContext:
        title: str

        @property
        def dangerous(self):
            raise AssertionError("arbitrary properties must never be invoked")

    profile = profile_with(rule("title-check", target="title"))
    assert evaluate_profile_rules(profile, project=SafeContext("Present")) == ()
    unsafe = profile_with(rule("property-check", target="dangerous"))
    result = evaluate_profile_rules(unsafe, project=SafeContext("Present"))
    assert result[0].code == "PROFILE_RULE_REQUIRED"


def test_profile_and_selected_preset_rules_are_both_evaluated():
    preset = ProductionPreset(
        preset_id="documentary", display_name="Documentary",
        rules=(rule("preset-review", category="review", severity="warning",
                    operator="manual_review"),),
    )
    profile = profile_with(rule("profile-title"), presets=(preset,))
    results = evaluate_profile_rules(profile, project={}, selected_preset_id="documentary")
    assert [item.rule_id for item in results] == ["profile-title", "preset-review"]
    assert results[1].source == "preset:documentary"


def test_unknown_selected_preset_returns_diagnostic():
    results = evaluate_profile_rules(profile_with(), selected_preset_id="missing")
    assert results[0].code == "PROFILE_PRESET_NOT_FOUND"
    assert results[0].severity == "error"


def test_future_profile_is_not_evaluated():
    future = ChannelProfile.from_dict({
        "schema_version": 99, "profile_id": "future", "display_name": "Future",
        "new_rules": [{"run": "never"}],
    })
    results = evaluate_profile_rules(future, project={"title": "ignored"})
    assert results[0].code == "PROFILE_SCHEMA_UNSUPPORTED"


def test_missing_scope_input_is_not_treated_as_a_failure():
    profile = profile_with(rule("scene-needs-prompt", scope="scene", target="visual_prompt"))
    assert evaluate_profile_rules(profile, project={}) == ()


def test_builtin_review_rules_produce_diagnostics_for_supplied_contexts():
    rihvaya = get_builtin_profile("rihvaya")
    results = evaluate_profile_rules(
        rihvaya, project={}, scenes=[{"id": "s1"}],
        scene_plans={"s1": {"kind": "illustration"}},
        selected_preset_id="islamic_2d_cartoon_storytelling",
    )
    assert [item.code for item in results] == [
        "PROFILE_RULE_REVIEW_REQUIRED", "PROFILE_RULE_REVIEW_REQUIRED",
        "PROFILE_RULE_REVIEW_REQUIRED",
    ]


def test_diagnostics_are_immutable_and_serializable():
    result = evaluate_profile_rules(profile_with(rule("need-title")), project={})[0]
    assert isinstance(result, ProfileDiagnostic)
    assert result.to_dict()["code"] == result.code
    with pytest.raises((AttributeError, TypeError)):
        result.code = "changed"
