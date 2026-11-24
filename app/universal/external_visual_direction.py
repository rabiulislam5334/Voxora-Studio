"""Safe import and validation for external VXP-10.2 visual-direction packages.

The initial interchange format is the versioned JSON representation emitted by
DirectorPlan.to_dict(). Imports are proposals only: they are bound to the exact
script, profile and narration source and always require explicit user approval
before the existing Auto Produce handoff can consume them.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.universal.production_director import (
    DirectorIntent,
    DirectorPlan,
    DirectorScene,
    DirectorShot,
    SceneRole,
)
from app.universal.storyboard import NarrationSource, StoryboardValidationError, TimingInterval


MAX_PACKAGE_BYTES = 10 * 1024 * 1024
MAX_SCENES = 1000
MAX_SHOTS = 5000
MAX_TEXT_LENGTH = 20_000


class VisualDirectionImportError(ValueError):
    """Raised when an external visual-direction package is unsafe or invalid."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VisualDirectionImportError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise VisualDirectionImportError(f"non-finite JSON number is not allowed: {value}")


def _read_package(package: Any) -> Mapping[str, Any]:
    if isinstance(package, Mapping):
        try:
            encoded = json.dumps(package, ensure_ascii=False, allow_nan=False).encode("utf-8")
            data = json.loads(encoded, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
        except (TypeError, ValueError, UnicodeError) as exc:
            if isinstance(exc, VisualDirectionImportError):
                raise
            raise VisualDirectionImportError(f"package must contain JSON-compatible values: {exc}") from exc
    elif isinstance(package, Path):
        if package.is_symlink():
            raise VisualDirectionImportError("visual-direction package must not be a symbolic link")
        try:
            path = package.expanduser().resolve(strict=True)
            if not path.is_file() or path.stat().st_size > MAX_PACKAGE_BYTES:
                raise VisualDirectionImportError("package must be a regular JSON file no larger than 10 MiB")
            raw = path.read_bytes()
        except OSError as exc:
            raise VisualDirectionImportError(f"cannot read visual-direction package: {exc}") from exc
        try:
            data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
        except (UnicodeError, json.JSONDecodeError, VisualDirectionImportError) as exc:
            raise VisualDirectionImportError(f"invalid visual-direction JSON: {exc}") from exc
    elif isinstance(package, str):
        if len(package.encode("utf-8")) > MAX_PACKAGE_BYTES:
            raise VisualDirectionImportError("visual-direction JSON exceeds the 10 MiB limit")
        try:
            data = json.loads(package, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
        except (UnicodeError, json.JSONDecodeError, VisualDirectionImportError) as exc:
            raise VisualDirectionImportError(f"invalid visual-direction JSON: {exc}") from exc
    else:
        raise VisualDirectionImportError("package must be a JSON object, JSON string, or pathlib.Path")
    if not isinstance(data, dict):
        raise VisualDirectionImportError("visual-direction package root must be an object")
    return data


def _text(value: Any, field: str, *, maximum: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise VisualDirectionImportError(f"{field} must be a non-empty string of at most {maximum} characters")
    return value


def _string_tuple(value: Any, field: str, *, maximum_items: int = 100) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise VisualDirectionImportError(f"{field} must be an array with at most {maximum_items} items")
    return tuple(_text(item, f"{field}[]", maximum=2000) for item in value)


def _timing(value: Any, field: str) -> TimingInterval:
    try:
        return TimingInterval.from_dict(value)
    except (StoryboardValidationError, TypeError, ValueError) as exc:
        raise VisualDirectionImportError(f"{field} is invalid: {exc}") from exc


def import_visual_direction_package(
    package: Any,
    *,
    script: str,
    profile_id: str,
    narration_source: NarrationSource,
) -> DirectorPlan:
    """Validate an external plan and return the existing DirectorPlan contract.

    External timestamps are retained as planning provenance. The Auto Produce
    handoff still maps approved shots to the measured aligned narration lines;
    this importer never treats package timing as measured audio alignment.
    """
    if not isinstance(script, str) or not script.strip():
        raise VisualDirectionImportError("the active script must be non-empty")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise VisualDirectionImportError("the active profile_id is required")
    if not isinstance(narration_source, NarrationSource):
        raise VisualDirectionImportError("narration_source must be the active NarrationSource")
    fingerprint = hashlib.sha256(script.encode("utf-8")).hexdigest()
    if narration_source.text != script or narration_source.source_fingerprint != fingerprint:
        raise VisualDirectionImportError("active NarrationSource does not match the supplied script")

    data = _read_package(package)
    if data.get("schema_version") != 1:
        raise VisualDirectionImportError("unsupported visual-direction schema_version; expected 1")
    source_id = _text(data.get("source_id"), "source_id", maximum=256)
    source_fingerprint = _text(data.get("source_fingerprint"), "source_fingerprint", maximum=64)
    if source_id != narration_source.source_id:
        raise VisualDirectionImportError("package source_id does not match the active narration source")
    if source_fingerprint != fingerprint:
        raise VisualDirectionImportError("package script fingerprint is stale or does not match")
    package_profile = _text(data.get("profile_id"), "profile_id", maximum=128)
    if package_profile != profile_id:
        raise VisualDirectionImportError("package profile_id does not match the active channel profile")
    style_family = _text(data.get("profile_style_family"), "profile_style_family", maximum=256)
    plan_id = _text(data.get("plan_id"), "plan_id", maximum=256)
    if data.get("requires_review") is not True:
        raise VisualDirectionImportError("external plans must require explicit review and approval")

    raw_shots = data.get("shots")
    raw_scenes = data.get("scenes")
    if not isinstance(raw_shots, list) or not raw_shots or len(raw_shots) > MAX_SHOTS:
        raise VisualDirectionImportError(f"shots must contain 1 to {MAX_SHOTS} entries")
    if not isinstance(raw_scenes, list) or not raw_scenes or len(raw_scenes) > MAX_SCENES:
        raise VisualDirectionImportError(f"scenes must contain 1 to {MAX_SCENES} entries")

    units = {unit.unit_id: unit for unit in narration_source.units}
    if len(units) != len(narration_source.units) or not units:
        raise VisualDirectionImportError("active narration units must have unique IDs")

    shots = []
    for index, item in enumerate(raw_shots):
        field = f"shots[{index}]"
        if not isinstance(item, dict):
            raise VisualDirectionImportError(f"{field} must be an object")
        shot_id = _text(item.get("shot_id"), f"{field}.shot_id", maximum=256)
        narration_ids = _string_tuple(item.get("narration_unit_ids"), f"{field}.narration_unit_ids")
        if not narration_ids or any(unit_id not in units for unit_id in narration_ids):
            raise VisualDirectionImportError(f"{field} references unknown narration units")
        try:
            intent = DirectorIntent(item.get("intent"))
        except (TypeError, ValueError):
            raise VisualDirectionImportError(f"{field}.intent is unsupported") from None
        confidence = item.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(float(confidence)) or not 0 <= confidence <= 1:
            raise VisualDirectionImportError(f"{field}.confidence must be finite and between 0 and 1")
        shot_style = _text(item.get("style_family"), f"{field}.style_family", maximum=256)
        if shot_style != style_family:
            raise VisualDirectionImportError(f"{field}.style_family must match profile_style_family")
        shots.append(DirectorShot(
            shot_id=shot_id,
            narration_unit_ids=narration_ids,
            timing=_timing(item.get("timing"), f"{field}.timing"),
            intent=intent,
            shot_type=_text(item.get("shot_type"), f"{field}.shot_type", maximum=256),
            visual_prompt=_text(item.get("visual_prompt"), f"{field}.visual_prompt"),
            action_cues=_string_tuple(item.get("action_cues"), f"{field}.action_cues"),
            style_family=shot_style,
            confidence=float(confidence),
            rationale=_string_tuple(item.get("rationale"), f"{field}.rationale"),
            tags=_string_tuple(item.get("tags", []), f"{field}.tags"),
        ))

    shot_ids = tuple(shot.shot_id for shot in shots)
    if len(set(shot_ids)) != len(shot_ids):
        raise VisualDirectionImportError("shot_id values must be unique")
    covered_units = tuple(unit_id for shot in shots for unit_id in shot.narration_unit_ids)
    expected_units = tuple(unit.unit_id for unit in narration_source.units)
    if covered_units != expected_units:
        raise VisualDirectionImportError("shots must cover every active narration unit exactly once and in source order")

    scenes = []
    for index, item in enumerate(raw_scenes):
        field = f"scenes[{index}]"
        if not isinstance(item, dict):
            raise VisualDirectionImportError(f"{field} must be an object")
        scene_shots = _string_tuple(item.get("shot_ids"), f"{field}.shot_ids", maximum_items=MAX_SHOTS)
        if not scene_shots or any(shot_id not in set(shot_ids) for shot_id in scene_shots):
            raise VisualDirectionImportError(f"{field} references unknown shots")
        scene_units = _string_tuple(item.get("narration_unit_ids"), f"{field}.narration_unit_ids", maximum_items=MAX_SHOTS)
        try:
            role = SceneRole(item.get("role"))
        except (TypeError, ValueError):
            raise VisualDirectionImportError(f"{field}.role is unsupported") from None
        scenes.append(DirectorScene(
            scene_id=_text(item.get("scene_id"), f"{field}.scene_id", maximum=256),
            title=_text(item.get("title"), f"{field}.title", maximum=500),
            role=role,
            purpose=_text(item.get("purpose"), f"{field}.purpose", maximum=2000),
            shot_ids=scene_shots,
            narration_unit_ids=scene_units,
            timing=_timing(item.get("timing"), f"{field}.timing"),
        ))

    scene_ids = tuple(scene.scene_id for scene in scenes)
    if len(set(scene_ids)) != len(scene_ids):
        raise VisualDirectionImportError("scene_id values must be unique")
    flattened_shots = tuple(shot_id for scene in scenes for shot_id in scene.shot_ids)
    if flattened_shots != shot_ids:
        raise VisualDirectionImportError("scenes must reference every shot exactly once and in source order")
    shot_by_id = {shot.shot_id: shot for shot in shots}
    for scene in scenes:
        expected_scene_units = tuple(
            unit_id for shot_id in scene.shot_ids for unit_id in shot_by_id[shot_id].narration_unit_ids
        )
        if scene.narration_unit_ids != expected_scene_units:
            raise VisualDirectionImportError(f"scene {scene.scene_id} narration coverage does not match its shots")
        scene_shots = [shot_by_id[shot_id] for shot_id in scene.shot_ids]
        if scene.timing.start_ms != min(shot.timing.start_ms for shot in scene_shots) or scene.timing.end_ms != max(shot.timing.end_ms for shot in scene_shots):
            raise VisualDirectionImportError(f"scene {scene.scene_id} timing does not bound its shots")

    limitations = _string_tuple(data.get("limitations", []), "limitations", maximum_items=50)
    return DirectorPlan(
        plan_id=plan_id,
        source_id=source_id,
        source_fingerprint=source_fingerprint,
        profile_id=package_profile,
        profile_style_family=style_family,
        scenes=tuple(scenes),
        shots=tuple(shots),
        requires_review=True,
        limitations=limitations,
    )
