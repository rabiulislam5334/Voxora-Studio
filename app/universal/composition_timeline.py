"""Immutable composition-backed scene render timeline snapshots.

This module maps approved, persisted still compositions to the existing
StudioState scene timeline. It is planning-only: it does not render frames,
mix audio, mutate projects, or select/fallback between engines.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from app.core.timebase import (
    TICKS_PER_SECOND,
    seconds_to_ticks,
    ticks_to_frames,
    ticks_to_seconds,
)
from app.models.project import Project
from app.studio.models import StudioState
from app.studio.timing import SceneTimingInput, compute_timeline
from app.universal.composition import SceneComposition
from app.universal.composition_workflow import (
    SCENE_COMPOSITIONS_KEY,
    SCENE_COMPOSITION_STORAGE_VERSION,
    preview_scene_composition,
)
from app.universal.models import UniversalState

COMPOSITION_TIMELINE_PLAN_VERSION = 1


class CompositionTimelinePlanError(ValueError):
    """Raised when a composition-backed timeline cannot be planned safely."""


class StaleCompositionTimelinePlanError(CompositionTimelinePlanError):
    """Raised when project, composition, timing, or asset inputs changed."""


@dataclass(frozen=True)
class TimelinePlanDiagnostic:
    code: str
    severity: str
    message: str
    scene_id: Optional[str] = None


@dataclass(frozen=True)
class TimelineAssetSnapshot:
    asset_id: str
    kind: str
    path: Optional[str]
    identity: Optional[str]


@dataclass(frozen=True)
class CompositionSceneSlot:
    scene_id: str
    scene_order: int
    composition_id: Optional[str]
    composition_fingerprint: Optional[str]
    composition_target_fingerprint: Optional[str]
    assets: Tuple[TimelineAssetSnapshot, ...]
    start_ticks: int
    slot_ticks: int
    segment_ticks: int
    end_ticks: int
    segment_end_ticks: int
    frame_start: int
    frame_end: int
    segment_frame_end: int
    narration_duration_ticks: Optional[int]
    pause_ticks: int
    timing_basis: str
    extended_for_narration: bool


@dataclass(frozen=True)
class CompositionTimelinePlan:
    project_id: str
    fps: int
    width: int
    height: int
    transition: str
    transition_ticks: int
    total_ticks: int
    total_frames: int
    slots: Tuple[CompositionSceneSlot, ...]
    diagnostics: Tuple[TimelinePlanDiagnostic, ...]
    input_fingerprint: str
    plan_fingerprint: str
    plan_version: int = COMPOSITION_TIMELINE_PLAN_VERSION

    @property
    def is_valid(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    @property
    def requires_review(self) -> bool:
        return any(item.severity in ("warning", "review") for item in self.diagnostics)


def _digest(payload: object) -> str:
    try:
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CompositionTimelinePlanError(
            f"timeline inputs cannot be fingerprinted safely: {exc}"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _require_tick_map(values: Optional[Mapping[str, int]], name: str) -> dict[str, int]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise CompositionTimelinePlanError(f"{name} must be a mapping of scene IDs to integer ticks")
    result = {}
    for scene_id, ticks in values.items():
        if not isinstance(scene_id, str) or not scene_id.strip():
            raise CompositionTimelinePlanError(f"{name} contains an invalid scene ID")
        if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 0:
            raise CompositionTimelinePlanError(f"{name}[{scene_id!r}] must be a non-negative integer tick count")
        result[scene_id] = ticks
    return result


def _stored_compositions(state: UniversalState) -> dict:
    raw = state.extra.get(SCENE_COMPOSITIONS_KEY, {})
    if not isinstance(raw, dict):
        raise CompositionTimelinePlanError("stored scene_compositions data is malformed")
    return raw


def _load_composition(scene_id: str, entry: object) -> SceneComposition:
    if not isinstance(entry, dict):
        raise CompositionTimelinePlanError(f"stored composition entry for scene {scene_id!r} is malformed")
    version = entry.get("storage_version", SCENE_COMPOSITION_STORAGE_VERSION)
    if isinstance(version, bool) or not isinstance(version, int) or version != SCENE_COMPOSITION_STORAGE_VERSION:
        raise CompositionTimelinePlanError(f"stored composition for scene {scene_id!r} has an unsupported storage version")
    raw = entry.get("composition")
    if not isinstance(raw, dict):
        raise CompositionTimelinePlanError(f"stored composition payload for scene {scene_id!r} is malformed")
    try:
        composition = SceneComposition.from_dict(raw)
    except (TypeError, ValueError) as exc:
        raise CompositionTimelinePlanError(f"stored composition for scene {scene_id!r} is invalid: {exc}") from exc
    if composition.scene_id != scene_id:
        raise CompositionTimelinePlanError(f"stored composition key does not match scene ID {scene_id!r}")
    expected = entry.get("composition_fingerprint")
    if expected is not None and expected != composition.fingerprint:
        raise CompositionTimelinePlanError(f"stored composition fingerprint is inconsistent for scene {scene_id!r}")
    return composition


def _project_input_fingerprint(
    project: Project,
    universal: UniversalState,
    studio: StudioState,
    narration: Mapping[str, int],
    pauses: Mapping[str, int],
) -> str:
    return _digest({
        "project_id": project.id,
        "scenes": [
            {
                "id": scene.id, "title": scene.title, "text": scene.text,
                "notes": scene.notes, "visual_prompt": scene.visual_prompt,
                "order": scene.order, "pause_ms": scene.pause_ms,
                "scene_pause_ms": scene.scene_pause_ms,
            }
            for scene in sorted(project.scenes, key=lambda item: (item.order, item.id))
        ],
        "universal": universal.to_dict(),
        "video": studio.video.to_dict(),
        "narration_duration_ticks": dict(sorted(narration.items())),
        "narration_pause_ticks": dict(sorted(pauses.items())),
    })


def build_composition_timeline_plan(
    project: Project,
    narration_duration_ticks: Mapping[str, int],
    *,
    narration_pause_ticks: Optional[Mapping[str, int]] = None,
) -> CompositionTimelinePlan:
    """Build a deterministic read-only render timeline for persisted compositions.

    Narration durations are measured durations in canonical project ticks.
    Missing narration timings are not fabricated: the existing configured or
    default scene duration is used and a review diagnostic is emitted.
    Composition persistence is already an explicit user-approved operation;
    this builder itself is read-only and does not imply render approval.
    """
    if not isinstance(project, Project):
        raise CompositionTimelinePlanError("project must be a Project")
    if not isinstance(project.settings, dict):
        raise CompositionTimelinePlanError("project.settings must be an object")

    narration = _require_tick_map(narration_duration_ticks, "narration_duration_ticks")
    pauses = _require_tick_map(narration_pause_ticks, "narration_pause_ticks")
    scene_ids = [scene.id for scene in project.scenes]
    if any(not isinstance(scene_id, str) or not scene_id.strip() for scene_id in scene_ids):
        raise CompositionTimelinePlanError("every project scene must have a non-empty ID")
    if len(scene_ids) != len(set(scene_ids)):
        raise CompositionTimelinePlanError("project scene IDs must be unique")
    unknown_narration = sorted(set(narration) - set(scene_ids))
    unknown_pauses = sorted(set(pauses) - set(scene_ids))
    if unknown_narration or unknown_pauses:
        unknown = sorted(set(unknown_narration + unknown_pauses))
        raise CompositionTimelinePlanError(
            "timing inputs reference unknown scenes: " + ", ".join(unknown)
        )

    universal = UniversalState.from_project_settings(project.settings)
    if universal.read_only:
        raise CompositionTimelinePlanError("Universal project data is read-only")
    studio = StudioState.from_project_settings(project.settings)
    if studio.read_only:
        raise CompositionTimelinePlanError("Studio timeline settings are malformed or read-only")
    if not project.scenes:
        raise CompositionTimelinePlanError("project must contain at least one scene")

    compositions = _stored_compositions(universal)
    known_scene_ids = set(scene_ids)
    stale_composition_ids = sorted(set(compositions) - known_scene_ids)
    diagnostics = [
        TimelinePlanDiagnostic(
            "ORPHANED_SCENE_COMPOSITION", "warning",
            "A stored composition belongs to a scene that no longer exists.",
            scene_id,
        )
        for scene_id in stale_composition_ids
    ]

    ordered_scenes = sorted(project.scenes, key=lambda item: (item.order, item.id))
    timing_inputs = []
    pause_by_scene = {}
    timing_basis_by_scene = {}
    for scene in ordered_scenes:
        narration_ticks = narration.get(scene.id)
        pause_ticks = pauses.get(
            scene.id,
            seconds_to_ticks(scene.pause_ms / 1000, rounding="half_up")
            if isinstance(scene.pause_ms, int) and not isinstance(scene.pause_ms, bool) and scene.pause_ms >= 0
            else 0,
        )
        pause_by_scene[scene.id] = pause_ticks
        setting = studio.video.scene(scene.id)
        configured_ticks = (
            seconds_to_ticks(setting.duration_s, rounding="half_up")
            if setting.duration_s is not None else None
        )
        if narration_ticks is not None:
            timing_basis_by_scene[scene.id] = (
                "configured_floor"
                if configured_ticks is not None and configured_ticks > narration_ticks + pause_ticks
                else "measured_narration"
            )
        elif configured_ticks is not None:
            timing_basis_by_scene[scene.id] = "configured"
            diagnostics.append(TimelinePlanDiagnostic(
                "NARRATION_TIMING_MISSING", "warning",
                "No measured narration duration was supplied; the configured scene duration is used.",
                scene.id,
            ))
        else:
            timing_basis_by_scene[scene.id] = "default_estimate"
            diagnostics.append(TimelinePlanDiagnostic(
                "SCENE_DURATION_ESTIMATED", "review",
                "No measured narration or configured duration was supplied; the Studio default duration is used.",
                scene.id,
            ))
        timing_inputs.append(SceneTimingInput(
            scene_id=scene.id,
            narration_s=ticks_to_seconds(narration_ticks) if narration_ticks is not None else None,
            configured_s=ticks_to_seconds(configured_ticks) if configured_ticks is not None else None,
            pause_s=ticks_to_seconds(pause_ticks),
        ))

    timeline = compute_timeline(
        timing_inputs,
        transition=studio.video.transition,
        transition_s=studio.video.transition_s,
        default_duration_s=studio.video.default_duration_s,
    )
    fps = studio.video.fps
    width, height = studio.video.size
    slots = []
    for scene, timing in zip(ordered_scenes, timeline.slots):
        entry = compositions.get(scene.id)
        composition = None
        preview = None
        assets: Tuple[TimelineAssetSnapshot, ...] = ()
        if entry is None:
            diagnostics.append(TimelinePlanDiagnostic(
                "SCENE_COMPOSITION_MISSING", "error",
                "This scene has no explicitly persisted composition.",
                scene.id,
            ))
        else:
            try:
                composition = _load_composition(scene.id, entry)
                preview = preview_scene_composition(project, composition)
                if not preview.is_valid:
                    for item in preview.diagnostics:
                        if item.severity == "error":
                            diagnostics.append(TimelinePlanDiagnostic(
                                "COMPOSITION_BINDING_INVALID", "error",
                                item.message, scene.id,
                            ))
                plan = universal.scene_plans.get(scene.id)
                refs = {ref.asset_id: ref for ref in plan.asset_refs} if plan else {}
                used_ids = sorted({element.asset_id for element in composition.elements})
                assets = tuple(
                    TimelineAssetSnapshot(
                        asset_id=asset_id,
                        kind=refs[asset_id].kind,
                        path=refs[asset_id].path,
                        identity=refs[asset_id].identity,
                    )
                    for asset_id in used_ids if asset_id in refs
                )
            except CompositionTimelinePlanError as exc:
                diagnostics.append(TimelinePlanDiagnostic(
                    "COMPOSITION_INVALID", "error", str(exc), scene.id,
                ))
            except (TypeError, ValueError) as exc:
                diagnostics.append(TimelinePlanDiagnostic(
                    "COMPOSITION_INVALID", "error", str(exc), scene.id,
                ))

        end_ticks = timing.start_ticks + timing.slot_ticks
        segment_end_ticks = timing.start_ticks + timing.segment_ticks
        frame_start = ticks_to_frames(timing.start_ticks, fps, rounding="half_up")
        frame_end = ticks_to_frames(end_ticks, fps, rounding="half_up")
        segment_frame_end = ticks_to_frames(segment_end_ticks, fps, rounding="half_up")
        if frame_end <= frame_start:
            diagnostics.append(TimelinePlanDiagnostic(
                "SCENE_FRAME_INTERVAL_EMPTY", "error",
                "Scene timing maps to an empty frame interval at the selected frame rate.",
                scene.id,
            ))
        slots.append(CompositionSceneSlot(
            scene_id=scene.id,
            scene_order=scene.order,
            composition_id=composition.composition_id if composition else None,
            composition_fingerprint=composition.fingerprint if composition else None,
            composition_target_fingerprint=preview.target_fingerprint if preview else None,
            assets=assets,
            start_ticks=timing.start_ticks,
            slot_ticks=timing.slot_ticks,
            segment_ticks=timing.segment_ticks,
            end_ticks=end_ticks,
            segment_end_ticks=segment_end_ticks,
            frame_start=frame_start,
            frame_end=frame_end,
            segment_frame_end=segment_frame_end,
            narration_duration_ticks=narration.get(scene.id),
            pause_ticks=pause_by_scene[scene.id],
            timing_basis=timing_basis_by_scene[scene.id],
            extended_for_narration=timing.extended,
        ))

    diagnostics.sort(key=lambda item: (
        item.scene_id or "", item.code, item.severity, item.message
    ))
    input_fingerprint = _project_input_fingerprint(
        project, universal, studio, narration, pauses,
    )
    plan_payload = {
        "plan_version": COMPOSITION_TIMELINE_PLAN_VERSION,
        "project_id": project.id,
        "fps": fps, "width": width, "height": height,
        "transition": studio.video.transition,
        "transition_ticks": timeline.transition_ticks,
        "total_ticks": timeline.total_ticks,
        "total_frames": ticks_to_frames(timeline.total_ticks, fps, rounding="half_up"),
        "slots": [
            {
                "scene_id": item.scene_id, "scene_order": item.scene_order,
                "composition_id": item.composition_id,
                "composition_fingerprint": item.composition_fingerprint,
                "composition_target_fingerprint": item.composition_target_fingerprint,
                "assets": [
                    {"asset_id": asset.asset_id, "kind": asset.kind,
                     "path": asset.path, "identity": asset.identity}
                    for asset in item.assets
                ],
                "start_ticks": item.start_ticks, "slot_ticks": item.slot_ticks,
                "segment_ticks": item.segment_ticks, "end_ticks": item.end_ticks,
                "segment_end_ticks": item.segment_end_ticks,
                "frame_start": item.frame_start, "frame_end": item.frame_end,
                "segment_frame_end": item.segment_frame_end,
                "narration_duration_ticks": item.narration_duration_ticks,
                "pause_ticks": item.pause_ticks, "timing_basis": item.timing_basis,
                "extended_for_narration": item.extended_for_narration,
            }
            for item in slots
        ],
        "diagnostics": [
            {"code": item.code, "severity": item.severity,
             "message": item.message, "scene_id": item.scene_id}
            for item in diagnostics
        ],
        "input_fingerprint": input_fingerprint,
    }
    return CompositionTimelinePlan(
        project_id=project.id,
        fps=fps, width=width, height=height,
        transition=studio.video.transition,
        transition_ticks=timeline.transition_ticks,
        total_ticks=timeline.total_ticks,
        total_frames=ticks_to_frames(timeline.total_ticks, fps, rounding="half_up"),
        slots=tuple(slots),
        diagnostics=tuple(diagnostics),
        input_fingerprint=input_fingerprint,
        plan_fingerprint=_digest(plan_payload),
    )


def assert_composition_timeline_plan_current(
    project: Project,
    plan: CompositionTimelinePlan,
    narration_duration_ticks: Mapping[str, int],
    *,
    narration_pause_ticks: Optional[Mapping[str, int]] = None,
) -> None:
    """Reject a plan if any project, timing, composition, or asset input changed."""
    if not isinstance(plan, CompositionTimelinePlan):
        raise CompositionTimelinePlanError("plan must be a CompositionTimelinePlan")
    current = build_composition_timeline_plan(
        project, narration_duration_ticks,
        narration_pause_ticks=narration_pause_ticks,
    )
    if (
        current.project_id != plan.project_id
        or current.input_fingerprint != plan.input_fingerprint
        or current.plan_fingerprint != plan.plan_fingerprint
    ):
        raise StaleCompositionTimelinePlanError(
            "composition timeline plan is stale; rebuild and review it before rendering"
        )
    if not current.is_valid:
        raise CompositionTimelinePlanError(
            "composition timeline plan contains blocking diagnostics"
        )
