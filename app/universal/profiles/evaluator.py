"""Pure, deterministic evaluation of declarative channel production rules.

The evaluator reports diagnostics only and never mutates project data, scenes,
scene plans, profile documents, or approval state.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from app.universal.profiles.models import ChannelProfile, ProductionRule

_MISSING = object()
_SUPPORTED_OPERATORS = frozenset({
    "exists", "equals", "not_equals", "in", "not_in", "contains", "manual_review"
})


@dataclass(frozen=True)
class ProfileDiagnostic:
    """One stable, machine-readable result from profile rule evaluation."""

    code: str
    severity: str
    message: str
    rule_id: str | None = None
    scope: str | None = None
    subject_id: str | None = None
    source: str = "profile"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "rule_id": self.rule_id,
            "scope": self.scope,
            "subject_id": self.subject_id,
            "source": self.source,
        }


def _read_target(context: Any, target: str) -> Any:
    """Read a dotted path from mappings or declared dataclass fields only."""
    current = context
    for part in target.split("."):
        if not part or part.startswith("_"):
            return _MISSING
        if isinstance(current, Mapping):
            current = current.get(part, _MISSING)
        elif is_dataclass(current) and not isinstance(current, type):
            allowed = {item.name for item in fields(current)}
            if part not in allowed:
                return _MISSING
            current = getattr(current, part)
        else:
            return _MISSING
        if current is _MISSING:
            return _MISSING
    return current


def _is_present(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, (str, bytes, list, tuple, dict, set, frozenset)):
        return len(value) > 0
    return True


def _matches(operator: str, actual: Any, expected: Any) -> bool:
    if operator == "exists":
        return _is_present(actual)
    if actual is _MISSING:
        return False
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "in":
        return isinstance(expected, (list, tuple, set, frozenset, str)) and actual in expected
    if operator == "not_in":
        return isinstance(expected, (list, tuple, set, frozenset, str)) and actual not in expected
    if operator == "contains":
        if isinstance(actual, Mapping):
            return expected in actual
        if isinstance(actual, (list, tuple, set, frozenset, str)):
            try:
                return expected in actual
            except (TypeError, ValueError):
                return False
        return False
    return False


def _subjects(value: Any) -> list[tuple[str | None, Any]]:
    """Normalize a scope collection while preserving caller-provided order."""
    if isinstance(value, Mapping):
        return [(str(key), item) for key, item in value.items()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = []
        for index, item in enumerate(value):
            identifier = _read_target(item, "id")
            if identifier is _MISSING:
                identifier = _read_target(item, "scene_id")
            result.append((str(identifier) if identifier is not _MISSING else str(index), item))
        return result
    return []


def _evaluate_rule(
    rule: ProductionRule,
    *,
    context: Any,
    subject_id: str | None,
    source: str,
    completed_reviews: frozenset[str],
) -> ProfileDiagnostic | None:
    if rule.operator not in _SUPPORTED_OPERATORS:
        return ProfileDiagnostic(
            "PROFILE_RULE_UNSUPPORTED", "warning",
            f"Rule '{rule.rule_id}' uses an unsupported operator and was not executed.",
            rule.rule_id, rule.scope, subject_id, source,
        )

    if rule.operator == "manual_review":
        if rule.rule_id in completed_reviews:
            return None
        return ProfileDiagnostic(
            "PROFILE_RULE_REVIEW_REQUIRED", rule.severity, rule.message,
            rule.rule_id, rule.scope, subject_id, source,
        )

    actual = _read_target(context, rule.target)
    matched = _matches(rule.operator, actual, rule.expected)
    if rule.category == "prohibited":
        violated = matched
        code = "PROFILE_RULE_PROHIBITED"
    else:
        violated = not matched
        code = {
            "required": "PROFILE_RULE_REQUIRED",
            "recommended": "PROFILE_RULE_RECOMMENDED",
        }.get(rule.category, "PROFILE_RULE_UNSUPPORTED")

    if not violated:
        return None
    return ProfileDiagnostic(
        code, rule.severity, rule.message, rule.rule_id,
        rule.scope, subject_id, source,
    )


def evaluate_profile_rules(
    profile: ChannelProfile,
    *,
    project: Any = None,
    scenes: Any = None,
    scene_plans: Any = None,
    selected_preset_id: str | None = None,
    completed_reviews: Sequence[str] | set[str] | frozenset[str] = (),
) -> tuple[ProfileDiagnostic, ...]:
    """Evaluate profile and optional preset rules against supplied data.

    A rule is evaluated only when its scope context is supplied. Scene and
    scene-plan collections may be ordered sequences or mappings keyed by IDs.
    Targets are dotted paths through mappings or declared dataclass fields;
    arbitrary properties and executable code are never invoked.

    completed_reviews contains rule IDs explicitly reviewed by a human. This
    is evaluation input only and does not update project approval state.
    """
    if not isinstance(profile, ChannelProfile):
        raise TypeError("profile must be a ChannelProfile")
    if profile.read_only:
        return (ProfileDiagnostic(
            "PROFILE_SCHEMA_UNSUPPORTED", "warning",
            "This profile uses an unsupported future schema and its rules were not evaluated.",
            source="profile",
        ),)

    try:
        review_ids = frozenset(completed_reviews)
    except TypeError as exc:
        raise TypeError("completed_reviews must be an iterable of rule IDs") from exc
    if not all(isinstance(item, str) for item in review_ids):
        raise TypeError("completed_reviews must contain only strings")

    rules: list[tuple[ProductionRule, str]] = [(rule, "profile") for rule in profile.rules]
    if selected_preset_id is not None:
        preset = next((item for item in profile.presets if item.preset_id == selected_preset_id), None)
        if preset is None:
            return (ProfileDiagnostic(
                "PROFILE_PRESET_NOT_FOUND", "error",
                f"Production preset '{selected_preset_id}' does not exist in profile '{profile.profile_id}'.",
                source="preset",
            ),)
        rules.extend((rule, f"preset:{preset.preset_id}") for rule in preset.rules)

    diagnostics: list[ProfileDiagnostic] = []
    contexts = {
        "project": [(None, project)] if project is not None else [],
        "scene": _subjects(scenes),
        "scene_plan": _subjects(scene_plans),
    }
    for rule, source in rules:
        for subject_id, context in contexts[rule.scope]:
            diagnostic = _evaluate_rule(
                rule,
                context=context,
                subject_id=subject_id,
                source=source,
                completed_reviews=review_ids,
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
    return tuple(diagnostics)
