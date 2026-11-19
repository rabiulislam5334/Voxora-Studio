"""Preflight checks for the opt-in Universal motion production workflow.

The report is read-only: it verifies the saved timeline/compositions, resolves
all referenced local assets through the managed catalog, and checks renderer
limits before narration generation or frame rendering starts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.project import Project
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import SceneComposition
from app.universal.composition_workflow import (
    SCENE_COMPOSITIONS_KEY,
    SCENE_COMPOSITION_STORAGE_VERSION,
    preview_scene_composition,
)
from app.universal.motion_raster_renderer import MotionRasterRenderer
from app.universal.production_workflow import (
    ProjectMotionProductionError,
    build_automatic_motion_plan,
)
from app.universal.raster_renderer import (
    RasterRenderError,
    resolve_scene_composition_assets,
)
from app.universal.composition_timeline import build_composition_timeline_plan
from app.universal.models import UniversalState


@dataclass(frozen=True)
class ProduceReadinessIssue:
    severity: str
    code: str
    message: str
    scene_id: Optional[str] = None


@dataclass(frozen=True)
class UniversalProduceReadinessReport:
    issues: tuple[ProduceReadinessIssue, ...]
    scene_count: int
    asset_count: int
    total_frames: int
    fps: int

    @property
    def is_ready(self) -> bool:
        return not any(item.severity == "error" for item in self.issues)

    @property
    def error_count(self) -> int:
        return sum(item.severity == "error" for item in self.issues)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.issues)


def inspect_universal_produce_readiness(
    project: Project,
    asset_library: VisualAssetLibrary,
    *,
    max_frames_per_scene: Optional[int] = None,
) -> UniversalProduceReadinessReport:
    """Inspect a Universal project without mutation, generation, or rendering.

    Asset resolution uses the same managed-library identity/hash checks as the
    renderer. A successful report means the project passed preflight only; it
    does not claim that FFmpeg encoding or the complete render has succeeded.
    """
    if not isinstance(project, Project):
        raise TypeError("project must be a Project")
    if not isinstance(asset_library, VisualAssetLibrary):
        raise TypeError("asset_library must be a VisualAssetLibrary")
    if max_frames_per_scene is None:
        max_frames_per_scene = MotionRasterRenderer().max_sequence_frames
    if (
        isinstance(max_frames_per_scene, bool)
        or not isinstance(max_frames_per_scene, int)
        or max_frames_per_scene <= 0
    ):
        raise ValueError("max_frames_per_scene must be a positive integer")

    issues: list[ProduceReadinessIssue] = []
    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        return UniversalProduceReadinessReport((
            ProduceReadinessIssue(
                "error", "UNIVERSAL_STATE_READ_ONLY",
                "Universal project data is malformed or from an unsupported future version.",
            ),
        ), 0, 0, 0, 0)

    try:
        plan = build_composition_timeline_plan(project, {})
    except (TypeError, ValueError) as exc:
        return UniversalProduceReadinessReport((
            ProduceReadinessIssue(
                "error", "TIMELINE_PLAN_INVALID",
                f"Could not build the composition timeline: {exc}",
            ),
        ), 0, 0, 0, 0)

    for diagnostic in plan.diagnostics:
        if diagnostic.severity in ("error", "warning"):
            issues.append(ProduceReadinessIssue(
                diagnostic.severity,
                diagnostic.code,
                diagnostic.message,
                diagnostic.scene_id,
            ))

    stored = state.extra.get(SCENE_COMPOSITIONS_KEY, {})
    if not isinstance(stored, dict):
        issues.append(ProduceReadinessIssue(
            "error", "COMPOSITION_STORAGE_INVALID",
            "Saved scene composition storage is malformed.",
        ))
        stored = {}

    resolved_asset_ids: set[str] = set()
    for slot in plan.slots:
        entry = stored.get(slot.scene_id)
        if not isinstance(entry, dict):
            # The timeline builder normally reports this too; retain a
            # scene-specific diagnostic so the checklist remains actionable.
            issues.append(ProduceReadinessIssue(
                "error", "COMPOSITION_MISSING",
                f"Scene '{slot.scene_id}' has no saved composition.",
                slot.scene_id,
            ))
            continue
        raw = entry.get("composition")
        if (
            entry.get("storage_version", SCENE_COMPOSITION_STORAGE_VERSION)
            != SCENE_COMPOSITION_STORAGE_VERSION
            or not isinstance(raw, dict)
        ):
            issues.append(ProduceReadinessIssue(
                "error", "COMPOSITION_UNSUPPORTED",
                f"Scene '{slot.scene_id}' has an unsupported or malformed saved composition.",
                slot.scene_id,
            ))
            continue
        try:
            composition = SceneComposition.from_dict(raw)
            preview = preview_scene_composition(project, composition)
        except (TypeError, ValueError) as exc:
            issues.append(ProduceReadinessIssue(
                "error", "COMPOSITION_INVALID",
                f"Scene '{slot.scene_id}' composition is invalid: {exc}",
                slot.scene_id,
            ))
            continue
        if not preview.is_valid:
            for diagnostic in preview.diagnostics:
                if diagnostic.severity == "error":
                    issues.append(ProduceReadinessIssue(
                        "error", diagnostic.code,
                        f"Scene '{slot.scene_id}': {diagnostic.message}",
                        slot.scene_id,
                    ))
            continue

        frame_count = slot.segment_frame_end - slot.frame_start
        if frame_count <= 0:
            issues.append(ProduceReadinessIssue(
                "error", "SCENE_FRAME_RANGE_INVALID",
                f"Scene '{slot.scene_id}' has no renderable frames.",
                slot.scene_id,
            ))
        elif frame_count > max_frames_per_scene:
            issues.append(ProduceReadinessIssue(
                "error", "SCENE_FRAME_LIMIT_EXCEEDED",
                f"Scene '{slot.scene_id}' requires {frame_count} frames; "
                f"the current CPU renderer limit is {max_frames_per_scene} frames per scene. "
                "Shorten the scene or split it into smaller scenes.",
                slot.scene_id,
            ))

        try:
            resolved = resolve_scene_composition_assets(project, composition, asset_library)
            resolved_asset_ids.update(resolved)
        except (RasterRenderError, OSError, TypeError, ValueError) as exc:
            issues.append(ProduceReadinessIssue(
                "error", "SCENE_ASSET_NOT_READY",
                f"Scene '{slot.scene_id}' asset check failed: {exc}",
                slot.scene_id,
            ))

    if plan.is_valid:
        try:
            build_automatic_motion_plan(project, plan)
        except (ProjectMotionProductionError, TypeError, ValueError) as exc:
            issues.append(ProduceReadinessIssue(
                "error", "MOTION_PLAN_INVALID",
                f"Saved transition or camera-motion settings are not renderable: {exc}",
            ))

    return UniversalProduceReadinessReport(
        tuple(issues),
        len(plan.slots),
        len(resolved_asset_ids),
        plan.total_frames,
        plan.fps,
    )
