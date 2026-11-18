"""Versioned, data-only channel profile contracts.

Profiles describe creative defaults and declarative production rules. They do
not execute code, select engines, mutate projects, or invoke production tools.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

PROFILE_SCHEMA_VERSION = 1
RULE_CATEGORIES = frozenset({"required", "recommended", "prohibited", "review"})
RULE_SCOPES = frozenset({"project", "scene", "scene_plan"})
RULE_OPERATORS = frozenset({
    "exists", "equals", "not_equals", "in", "not_in", "contains", "manual_review"
})
RULE_SEVERITIES = frozenset({"error", "warning", "info"})
_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class ProfileValidationError(ValueError):
    """Raised when a channel profile document is malformed."""


def _json_copy(value: Any, path: str = "value") -> Any:
    """Return a defensive copy of JSON-compatible data; reject executable values."""
    if value is None or isinstance(value, (str, bool, int)):
        return copy.deepcopy(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProfileValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, list):
        return [_json_copy(item, f"{path}[]") for item in value]
    if isinstance(value, tuple):
        return [_json_copy(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        copied = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProfileValidationError(f"{path} keys must be strings")
            copied[key] = _json_copy(item, f"{path}.{key}")
        return copied
    raise ProfileValidationError(f"{path} must contain JSON-compatible data only")


def _string(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ProfileValidationError(f"{field_name} must be a string")
    if not allow_empty and not value.strip():
        raise ProfileValidationError(f"{field_name} must not be empty")
    return value


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ProfileValidationError(f"{field_name} must be a list of strings")
    result = tuple(_string(item, f"{field_name}[]") for item in value)
    if len(set(result)) != len(result):
        raise ProfileValidationError(f"{field_name} must not contain duplicates")
    return result


def _extra(data: Mapping[str, Any], known: set[str]) -> dict[str, Any]:
    return {key: _json_copy(value, f"extra.{key}") for key, value in data.items() if key not in known}


def _merge(data: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in extra.items():
        if key not in data:
            data[key] = _json_copy(value, f"extra.{key}")
    return data


@dataclass(frozen=True)
class VisualDefaults:
    style_family: str = "unspecified"
    style_tags: tuple[str, ...] = ()
    mood: tuple[str, ...] = ()
    composition_guidance: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _string(self.style_family, "visual_defaults.style_family")
        object.__setattr__(self, "style_tags", _string_tuple(self.style_tags, "visual_defaults.style_tags"))
        object.__setattr__(self, "mood", _string_tuple(self.mood, "visual_defaults.mood"))
        object.__setattr__(self, "composition_guidance", _string_tuple(
            self.composition_guidance, "visual_defaults.composition_guidance"
        ))
        object.__setattr__(self, "extra", _json_copy(self.extra, "visual_defaults.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "style_family": self.style_family,
            "style_tags": list(self.style_tags),
            "mood": list(self.mood),
            "composition_guidance": list(self.composition_guidance),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "VisualDefaults":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("visual_defaults must be an object")
        known = {"style_family", "style_tags", "mood", "composition_guidance"}
        return cls(
            style_family=data.get("style_family", "unspecified"),
            style_tags=_string_tuple(data.get("style_tags", []), "visual_defaults.style_tags"),
            mood=_string_tuple(data.get("mood", []), "visual_defaults.mood"),
            composition_guidance=_string_tuple(
                data.get("composition_guidance", []), "visual_defaults.composition_guidance"
            ),
            extra=_extra(data, known),
        )


@dataclass(frozen=True)
class ProductionDefaults:
    aspect_ratio: str | None = None
    resolution: str | None = None
    frame_rate: int | None = None
    audio_policy: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for name in ("aspect_ratio", "resolution", "audio_policy"):
            value = getattr(self, name)
            if value is not None:
                _string(value, f"production_defaults.{name}")
        if self.frame_rate is not None and (
            isinstance(self.frame_rate, bool) or not isinstance(self.frame_rate, int)
            or self.frame_rate <= 0 or self.frame_rate > 240
        ):
            raise ProfileValidationError("production_defaults.frame_rate must be an integer from 1 to 240")
        object.__setattr__(self, "extra", _json_copy(self.extra, "production_defaults.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "frame_rate": self.frame_rate,
            "audio_policy": self.audio_policy,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "ProductionDefaults":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("production_defaults must be an object")
        known = {"aspect_ratio", "resolution", "frame_rate", "audio_policy"}
        return cls(**{key: data.get(key) for key in known}, extra=_extra(data, known))


@dataclass(frozen=True)
class ProductionRule:
    rule_id: str
    category: str
    severity: str
    scope: str
    target: str
    operator: str
    message: str
    expected: Any = None
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for name in ("rule_id", "target", "message"):
            _string(getattr(self, name), f"rule.{name}")
        if not _PROFILE_ID.fullmatch(self.rule_id):
            raise ProfileValidationError("rule.rule_id must be a stable lowercase identifier")
        if self.category not in RULE_CATEGORIES:
            raise ProfileValidationError("rule.category is unsupported")
        if self.severity not in RULE_SEVERITIES:
            raise ProfileValidationError("rule.severity is unsupported")
        if self.scope not in RULE_SCOPES:
            raise ProfileValidationError("rule.scope is unsupported")
        if self.operator not in RULE_OPERATORS:
            raise ProfileValidationError("rule.operator is unsupported")
        if self.category == "review" and self.operator != "manual_review":
            raise ProfileValidationError("review rules must use the manual_review operator")
        if self.operator == "manual_review" and self.category != "review":
            raise ProfileValidationError("manual_review operator is reserved for review rules")
        object.__setattr__(self, "expected", _json_copy(self.expected, "rule.expected"))
        object.__setattr__(self, "extra", _json_copy(self.extra, "rule.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "scope": self.scope,
            "target": self.target,
            "operator": self.operator,
            "expected": _json_copy(self.expected, "rule.expected"),
            "message": self.message,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "ProductionRule":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("production rule must be an object")
        known = {"rule_id", "category", "severity", "scope", "target", "operator", "expected", "message"}
        required = ("rule_id", "category", "severity", "scope", "target", "operator", "message")
        missing = [key for key in required if key not in data]
        if missing:
            raise ProfileValidationError(f"production rule is missing: {', '.join(missing)}")
        return cls(**{key: data.get(key) for key in required},
                   expected=data.get("expected"), extra=_extra(data, known))


@dataclass(frozen=True)
class ProductionPreset:
    preset_id: str
    display_name: str
    description: str = ""
    visual_defaults: VisualDefaults = field(default_factory=VisualDefaults)
    narration_defaults: Mapping[str, Any] = field(default_factory=dict, compare=False)
    rules: tuple[ProductionRule, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for name in ("preset_id", "display_name"):
            _string(getattr(self, name), f"preset.{name}")
        if not _PROFILE_ID.fullmatch(self.preset_id):
            raise ProfileValidationError("preset.preset_id must be a stable lowercase identifier")
        _string(self.description, "preset.description", allow_empty=True)
        if not isinstance(self.visual_defaults, VisualDefaults):
            raise ProfileValidationError("preset.visual_defaults must be VisualDefaults")
        rules = tuple(self.rules)
        if not all(isinstance(rule, ProductionRule) for rule in rules):
            raise ProfileValidationError("preset.rules must contain ProductionRule objects")
        if len({rule.rule_id for rule in rules}) != len(rules):
            raise ProfileValidationError("preset rule IDs must be unique")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "narration_defaults", _json_copy(self.narration_defaults, "preset.narration_defaults"))
        object.__setattr__(self, "extra", _json_copy(self.extra, "preset.extra"))

    def to_dict(self) -> dict[str, Any]:
        return _merge({
            "preset_id": self.preset_id,
            "display_name": self.display_name,
            "description": self.description,
            "visual_defaults": self.visual_defaults.to_dict(),
            "narration_defaults": _json_copy(self.narration_defaults, "preset.narration_defaults"),
            "rules": [rule.to_dict() for rule in self.rules],
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "ProductionPreset":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("production preset must be an object")
        known = {"preset_id", "display_name", "description", "visual_defaults", "narration_defaults", "rules"}
        rules = data.get("rules", [])
        if not isinstance(rules, list):
            raise ProfileValidationError("preset.rules must be a list")
        return cls(
            preset_id=data.get("preset_id"),
            display_name=data.get("display_name"),
            description=data.get("description", ""),
            visual_defaults=VisualDefaults.from_dict(data.get("visual_defaults", {})),
            narration_defaults=data.get("narration_defaults", {}),
            rules=tuple(ProductionRule.from_dict(item) for item in rules),
            extra=_extra(data, known),
        )


@dataclass(frozen=True)
class ChannelProfile:
    profile_id: str
    display_name: str
    description: str = ""
    content_domains: tuple[str, ...] = ()
    audience: Mapping[str, Any] = field(default_factory=dict, compare=False)
    narration_defaults: Mapping[str, Any] = field(default_factory=dict, compare=False)
    visual_defaults: VisualDefaults = field(default_factory=VisualDefaults)
    production_defaults: ProductionDefaults = field(default_factory=ProductionDefaults)
    preferred_engines: tuple[str, ...] = ()
    rules: tuple[ProductionRule, ...] = ()
    presets: tuple[ProductionPreset, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    schema_version: int = PROFILE_SCHEMA_VERSION
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)
    read_only: bool = False
    raw_payload: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("profile_id", "display_name"):
            _string(getattr(self, name), f"profile.{name}")
        if not _PROFILE_ID.fullmatch(self.profile_id):
            raise ProfileValidationError("profile.profile_id must be a stable lowercase identifier")
        _string(self.description, "profile.description", allow_empty=True)
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ProfileValidationError("profile.schema_version must be a positive integer")
        object.__setattr__(self, "content_domains", _string_tuple(self.content_domains, "profile.content_domains"))
        object.__setattr__(self, "preferred_engines", _string_tuple(self.preferred_engines, "profile.preferred_engines"))
        for name in ("audience", "narration_defaults", "metadata", "extra"):
            object.__setattr__(self, name, _json_copy(getattr(self, name), f"profile.{name}"))
        if not isinstance(self.visual_defaults, VisualDefaults):
            raise ProfileValidationError("profile.visual_defaults must be VisualDefaults")
        if not isinstance(self.production_defaults, ProductionDefaults):
            raise ProfileValidationError("profile.production_defaults must be ProductionDefaults")
        rules, presets = tuple(self.rules), tuple(self.presets)
        if not all(isinstance(item, ProductionRule) for item in rules):
            raise ProfileValidationError("profile.rules must contain ProductionRule objects")
        if not all(isinstance(item, ProductionPreset) for item in presets):
            raise ProfileValidationError("profile.presets must contain ProductionPreset objects")
        if len({item.rule_id for item in rules}) != len(rules):
            raise ProfileValidationError("profile rule IDs must be unique")
        if len({item.preset_id for item in presets}) != len(presets):
            raise ProfileValidationError("profile preset IDs must be unique")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "presets", presets)
        if self.read_only:
            object.__setattr__(self, "raw_payload", _json_copy(self.raw_payload, "profile.raw_payload"))

    def to_dict(self) -> dict[str, Any]:
        if self.read_only:
            return _json_copy(self.raw_payload, "profile.raw_payload")
        return _merge({
            "schema_version": PROFILE_SCHEMA_VERSION,
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "description": self.description,
            "content_domains": list(self.content_domains),
            "audience": _json_copy(self.audience, "profile.audience"),
            "narration_defaults": _json_copy(self.narration_defaults, "profile.narration_defaults"),
            "visual_defaults": self.visual_defaults.to_dict(),
            "production_defaults": self.production_defaults.to_dict(),
            "preferred_engines": list(self.preferred_engines),
            "rules": [rule.to_dict() for rule in self.rules],
            "presets": [preset.to_dict() for preset in self.presets],
            "metadata": _json_copy(self.metadata, "profile.metadata"),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "ChannelProfile":
        if not isinstance(data, Mapping):
            raise ProfileValidationError("channel profile must be an object")
        version = data.get("schema_version", PROFILE_SCHEMA_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ProfileValidationError("profile.schema_version must be a positive integer")
        if version > PROFILE_SCHEMA_VERSION:
            # Do not interpret fields owned by a newer schema. Use safe wrapper
            # values while retaining the original document verbatim for export.
            return cls(
                profile_id="unsupported",
                display_name="Unsupported profile",
                schema_version=version,
                read_only=True,
                raw_payload=_json_copy(data, "profile"),
            )
        known = {
            "schema_version", "profile_id", "display_name", "description", "content_domains",
            "audience", "narration_defaults", "visual_defaults", "production_defaults",
            "preferred_engines", "rules", "presets", "metadata",
        }
        rules, presets = data.get("rules", []), data.get("presets", [])
        if not isinstance(rules, list) or not isinstance(presets, list):
            raise ProfileValidationError("profile.rules and profile.presets must be lists")
        return cls(
            profile_id=data.get("profile_id"),
            display_name=data.get("display_name"),
            description=data.get("description", ""),
            content_domains=_string_tuple(data.get("content_domains", []), "profile.content_domains"),
            audience=data.get("audience", {}),
            narration_defaults=data.get("narration_defaults", {}),
            visual_defaults=VisualDefaults.from_dict(data.get("visual_defaults", {})),
            production_defaults=ProductionDefaults.from_dict(data.get("production_defaults", {})),
            preferred_engines=_string_tuple(data.get("preferred_engines", []), "profile.preferred_engines"),
            rules=tuple(ProductionRule.from_dict(item) for item in rules),
            presets=tuple(ProductionPreset.from_dict(item) for item in presets),
            metadata=data.get("metadata", {}),
            schema_version=version,
            extra=_extra(data, known),
        )
