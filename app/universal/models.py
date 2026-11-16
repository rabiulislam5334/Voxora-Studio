"""Versioned, forward-compatible data contracts for Voxora Universal Core.

This module deliberately has no renderer, UI, or provider dependencies.  The
Universal Core payload lives at Project.settings["universal"] and is separate
from the legacy "studio" settings.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

UNIVERSAL_SETTINGS_KEY = "universal"
UNIVERSAL_FORMAT_VERSION = 1

PLAN_STATUSES = ("draft", "proposed", "approved", "needs_review")


def _copy_unknown(data: Dict[str, Any], known: frozenset) -> Dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in data.items() if key not in known}


def _merge_extra(data: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in extra.items():
        if key not in data:
            data[key] = copy.deepcopy(value)
    return data


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


@dataclass
class EngineChoice:
    """A requested engine and its explicit, reviewable fallback chain."""

    engine_id: Optional[str] = None
    fallback_chain: List[str] = field(default_factory=list)
    reason: str = ""
    chosen_by: str = "director"
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _merge_extra({
            "engine_id": self.engine_id,
            "fallback_chain": list(self.fallback_chain),
            "reason": self.reason,
            "chosen_by": self.chosen_by,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "EngineChoice":
        if not isinstance(data, dict):
            raise ValueError("engine_choice must be an object")
        engine_id = data.get("engine_id")
        reason = data.get("reason", "")
        chosen_by = data.get("chosen_by", "director")
        fallback = data.get("fallback_chain", [])
        if engine_id is not None and not isinstance(engine_id, str):
            raise ValueError("engine_choice.engine_id must be a string or null")
        if not isinstance(reason, str) or not isinstance(chosen_by, str):
            raise ValueError("engine_choice reason and chosen_by must be strings")
        if not _is_string_list(fallback):
            raise ValueError("engine_choice.fallback_chain must be a list of strings")
        return cls(engine_id, list(fallback), reason, chosen_by,
                   _copy_unknown(data, frozenset({"engine_id", "fallback_chain", "reason", "chosen_by"})))


@dataclass
class AssetRef:
    """Stable reference to an input asset; identity is used by render caching."""

    asset_id: str
    kind: str
    path: Optional[str] = None
    identity: Optional[str] = None
    license: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _merge_extra({
            "asset_id": self.asset_id,
            "kind": self.kind,
            "path": self.path,
            "identity": self.identity,
            "license": self.license,
            "metadata": copy.deepcopy(self.metadata),
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "AssetRef":
        if not isinstance(data, dict):
            raise ValueError("asset reference must be an object")
        asset_id, kind = data.get("asset_id"), data.get("kind")
        path, identity, license_name = data.get("path"), data.get("identity"), data.get("license")
        metadata = data.get("metadata", {})
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError("asset_ref.asset_id must be a non-empty string")
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("asset_ref.kind must be a non-empty string")
        if any(value is not None and not isinstance(value, str) for value in (path, identity, license_name)):
            raise ValueError("asset_ref path, identity and license must be strings or null")
        if not isinstance(metadata, dict):
            raise ValueError("asset_ref.metadata must be an object")
        return cls(asset_id, kind, path, identity, license_name, copy.deepcopy(metadata),
                   _copy_unknown(data, frozenset({"asset_id", "kind", "path", "identity", "license", "metadata"})))


@dataclass
class ScenePlan:
    """Universal visual intent for one Project Scene, keyed by its stable ID.

    kind and style_tags are intentionally open strings: new visual categories
    must not require a schema migration or constrain future channel profiles.
    """

    scene_id: str
    kind: str = "unspecified"
    style_tags: List[str] = field(default_factory=list)
    requirements: Dict[str, Any] = field(default_factory=dict)
    engine_choice: EngineChoice = field(default_factory=EngineChoice)
    camera: Dict[str, Any] = field(default_factory=dict)
    asset_refs: List[AssetRef] = field(default_factory=list)
    complexity_estimate: Optional[float] = None
    notes: str = ""
    plan_status: str = "draft"
    script_hash: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _merge_extra({
            "scene_id": self.scene_id,
            "kind": self.kind,
            "style_tags": list(self.style_tags),
            "requirements": copy.deepcopy(self.requirements),
            "engine_choice": self.engine_choice.to_dict(),
            "camera": copy.deepcopy(self.camera),
            "asset_refs": [asset.to_dict() for asset in self.asset_refs],
            "complexity_estimate": self.complexity_estimate,
            "notes": self.notes,
            "plan_status": self.plan_status,
            "script_hash": self.script_hash,
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any, *, scene_id: Optional[str] = None) -> "ScenePlan":
        if not isinstance(data, dict):
            raise ValueError("scene plan must be an object")
        stored_id = data.get("scene_id", scene_id)
        if not isinstance(stored_id, str) or not stored_id.strip():
            raise ValueError("scene_plan.scene_id must be a non-empty string")
        if scene_id is not None and stored_id != scene_id:
            raise ValueError("scene plan key does not match scene_id")
        kind, notes, status = data.get("kind", "unspecified"), data.get("notes", ""), data.get("plan_status", "draft")
        tags = data.get("style_tags", [])
        requirements, camera = data.get("requirements", {}), data.get("camera", {})
        raw_assets = data.get("asset_refs", [])
        complexity, script_hash = data.get("complexity_estimate"), data.get("script_hash")
        if not isinstance(kind, str) or not isinstance(notes, str) or not isinstance(status, str):
            raise ValueError("scene_plan kind, notes and plan_status must be strings")
        if not _is_string_list(tags):
            raise ValueError("scene_plan.style_tags must be a list of strings")
        if not isinstance(requirements, dict) or not isinstance(camera, dict):
            raise ValueError("scene_plan requirements and camera must be objects")
        if not isinstance(raw_assets, list):
            raise ValueError("scene_plan.asset_refs must be a list")
        if complexity is not None:
            if isinstance(complexity, bool) or not isinstance(complexity, (int, float)):
                raise ValueError("scene_plan.complexity_estimate must be a finite number or null")
            try:
                complexity_value = float(complexity)
            except (OverflowError, ValueError):
                raise ValueError("scene_plan.complexity_estimate must be a finite number or null")
            if not math.isfinite(complexity_value):
                raise ValueError("scene_plan.complexity_estimate must be a finite number or null")
        else:
            complexity_value = None
        if status not in PLAN_STATUSES:
            raise ValueError("scene_plan.plan_status is not a supported status")
        if script_hash is not None and not isinstance(script_hash, str):
            raise ValueError("scene_plan.script_hash must be a string or null")
        return cls(
            scene_id=stored_id,
            kind=kind,
            style_tags=list(tags),
            requirements=copy.deepcopy(requirements),
            engine_choice=EngineChoice.from_dict(data.get("engine_choice", {})),
            camera=copy.deepcopy(camera),
            asset_refs=[AssetRef.from_dict(item) for item in raw_assets],
            complexity_estimate=complexity_value,
            notes=notes,
            plan_status=status,
            script_hash=script_hash,
            extra=_copy_unknown(data, frozenset({
                "scene_id", "kind", "style_tags", "requirements", "engine_choice",
                "camera", "asset_refs", "complexity_estimate", "notes", "plan_status", "script_hash",
            })),
        )


@dataclass
class UniversalState:
    """Project-level Universal Core payload with safe forward-version handling."""

    profile_id: Optional[str] = None
    scene_plans: Dict[str, ScenePlan] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)
    format_version: int = UNIVERSAL_FORMAT_VERSION
    read_only: bool = False
    raw_payload: Any = None

    def to_dict(self) -> Dict[str, Any]:
        if self.read_only:
            return copy.deepcopy(self.raw_payload)
        return _merge_extra({
            "format_version": UNIVERSAL_FORMAT_VERSION,
            "profile_id": self.profile_id,
            "scene_plans": {key: plan.to_dict() for key, plan in self.scene_plans.items()},
        }, self.extra)

    @classmethod
    def from_dict(cls, data: Any) -> "UniversalState":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            return cls(read_only=True, raw_payload=copy.deepcopy(data))
        version = data.get("format_version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            return cls(read_only=True, raw_payload=copy.deepcopy(data))
        if version > UNIVERSAL_FORMAT_VERSION:
            return cls(format_version=version, read_only=True, raw_payload=copy.deepcopy(data))
        profile_id = data.get("profile_id")
        plans_data = data.get("scene_plans", {})
        if profile_id is not None and not isinstance(profile_id, str):
            return cls(format_version=version, read_only=True, raw_payload=copy.deepcopy(data))
        if not isinstance(plans_data, dict):
            return cls(format_version=version, read_only=True, raw_payload=copy.deepcopy(data))
        try:
            plans = {key: ScenePlan.from_dict(value, scene_id=key) for key, value in plans_data.items()
                     if isinstance(key, str) and key.strip()}
            if len(plans) != len(plans_data):
                raise ValueError("scene_plans keys must be non-empty strings")
        except (TypeError, ValueError, OverflowError):
            return cls(format_version=version, read_only=True, raw_payload=copy.deepcopy(data))
        return cls(
            profile_id=profile_id,
            scene_plans=plans,
            extra=_copy_unknown(data, frozenset({"format_version", "profile_id", "scene_plans"})),
            format_version=version,
        )

    @classmethod
    def from_project_settings(cls, settings: Any) -> "UniversalState":
        if not isinstance(settings, dict):
            return cls()
        return cls.from_dict(settings.get(UNIVERSAL_SETTINGS_KEY))

    def prune_scenes(self, valid_scene_ids) -> None:
        """Remove plans for scenes that no longer exist in the owning project."""
        if self.read_only:
            return
        valid = set(valid_scene_ids)
        self.scene_plans = {key: plan for key, plan in self.scene_plans.items() if key in valid}

    def duplicate_scene_plan(self, source_scene_id: str, target_scene_id: str) -> Optional[ScenePlan]:
        """Copy visual intent to a newly-created scene without sharing mutable data."""
        if self.read_only or source_scene_id not in self.scene_plans:
            return None
        cloned = ScenePlan.from_dict(self.scene_plans[source_scene_id].to_dict())
        cloned.scene_id = target_scene_id
        cloned.plan_status = "draft"
        self.scene_plans[target_scene_id] = cloned
        return cloned

    def apply_to_project_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deep-copied settings dict with the Universal payload applied."""
        result = copy.deepcopy(settings)
        if not self.read_only:
            result[UNIVERSAL_SETTINGS_KEY] = self.to_dict()
        return result
