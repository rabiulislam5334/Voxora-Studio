"""Project-derived motion planning and timeline-aligned narration for Universal Produce.

This module connects persisted scene compositions, the immutable Studio timeline,
automatic deterministic camera motion, saved transition settings, and the existing
motion renderer/audio muxer. It never mutates project data or changes legacy
ProductionJob behavior.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

from app.audio.assembler import WavBuilder, wav_duration_ticks
from app.audio.ffmpeg_tool import FFmpegTool
from app.core import constants
from app.core.timebase import frames_to_ticks, ticks_to_samples
from app.models.project import Project
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import SceneComposition
from app.universal.composition_timeline import (
    CompositionTimelinePlan,
    CompositionTimelinePlanError,
    build_composition_timeline_plan,
)
from app.universal.composition_workflow import (
    SCENE_COMPOSITIONS_KEY,
    SCENE_COMPOSITION_STORAGE_VERSION,
    preview_scene_composition,
)
from app.universal.motion import MotionKeyframe, MotionTrack, SceneMotion
from app.universal.motion_timeline import (
    MotionTimelinePlan,
    MotionTimelineRenderCoordinator,
    MotionTimelineRenderResult,
    build_project_motion_timeline_plan,
)
from app.universal.models import UniversalState
from app.workers.cancel import CancelToken


AUTOMATIC_MOTION_VERSION = 1
AUTOMATIC_MOTION_PRESETS = (
    "zoom_in",
    "pan_left",
    "zoom_out",
    "pan_right",
    "pan_up",
    "zoom_in",
    "pan_down",
    "zoom_out",
)


class ProjectMotionProductionError(RuntimeError):
    """Raised when a project cannot be safely prepared or rendered."""


@dataclass(frozen=True)
class AutomaticMotionPlan:
    """Immutable generated scene motions and their transition-aware render plan."""

    project_id: str
    composition_plan_fingerprint: str
    scene_motions: tuple[tuple[str, SceneMotion], ...]
    motion_plan: MotionTimelinePlan
    generator_version: int = AUTOMATIC_MOTION_VERSION

    @property
    def motions(self) -> dict[str, SceneMotion]:
        """Return a fresh mapping so callers cannot mutate the stored plan."""
        return dict(self.scene_motions)


@dataclass(frozen=True)
class ProjectMotionProductionPlan:
    """Reviewed composition timeline plus deterministic automatic motion."""

    composition_plan: CompositionTimelinePlan
    automatic_motion: AutomaticMotionPlan

    @property
    def scene_motions(self) -> dict[str, SceneMotion]:
        return self.automatic_motion.motions

    @property
    def motion_plan(self) -> MotionTimelinePlan:
        return self.automatic_motion.motion_plan


def _keyframes(duration_frames: int, start: float, end: float) -> tuple[MotionKeyframe, ...]:
    if duration_frames <= 0:
        raise ProjectMotionProductionError("scene motion duration must be positive")
    first = MotionKeyframe(0, start, "ease_in_out")
    if duration_frames == 1:
        return (first,)
    return (first, MotionKeyframe(duration_frames - 1, end, "linear"))


def _scene_motion(scene_id: str, duration_frames: int, preset: str) -> SceneMotion:
    """Create a restrained camera move that stays inside the rendered image."""
    if preset == "zoom_in":
        zoom = (1.0, 1.08)
        pan_x = pan_y = None
    elif preset == "zoom_out":
        zoom = (1.08, 1.0)
        pan_x = pan_y = None
    elif preset == "pan_left":
        zoom = (1.06, 1.06)
        pan_x, pan_y = (0.02, -0.02), None
    elif preset == "pan_right":
        zoom = (1.06, 1.06)
        pan_x, pan_y = (-0.02, 0.02), None
    elif preset == "pan_up":
        zoom = (1.06, 1.06)
        pan_x, pan_y = None, (0.02, -0.02)
    elif preset == "pan_down":
        zoom = (1.06, 1.06)
        pan_x, pan_y = None, (-0.02, 0.02)
    else:
        raise ProjectMotionProductionError(f"unsupported automatic motion preset: {preset!r}")

    tracks = [
        MotionTrack(
            track_id="auto-camera-zoom",
            target_type="camera",
            target_id="camera",
            property_name="zoom",
            keyframes=_keyframes(duration_frames, *zoom),
        )
    ]
    if pan_x is not None:
        tracks.append(MotionTrack(
            track_id="auto-camera-pan-x",
            target_type="camera",
            target_id="camera",
            property_name="pan_x",
            keyframes=_keyframes(duration_frames, *pan_x),
        ))
    if pan_y is not None:
        tracks.append(MotionTrack(
            track_id="auto-camera-pan-y",
            target_type="camera",
            target_id="camera",
            property_name="pan_y",
            keyframes=_keyframes(duration_frames, *pan_y),
        ))
    return SceneMotion(
        scene_id=scene_id,
        duration_frames=duration_frames,
        tracks=tuple(tracks),
        extra={
            "generator": "voxora_automatic_camera",
            "generator_version": AUTOMATIC_MOTION_VERSION,
            "preset": preset,
        },
    )


def build_automatic_motion_plan(
    project: Project,
    composition_plan: CompositionTimelinePlan,
) -> AutomaticMotionPlan:
    """Derive deterministic camera motion from each approved saved composition.

    The planner is read-only. It validates stored composition fingerprints and
    target bindings again, uses the exact frame count (including outgoing
    transition overlap), and then delegates saved transition resolution to the
    existing immutable motion-timeline planner.
    """
    if not isinstance(project, Project):
        raise ProjectMotionProductionError("project must be a Project")
    if not isinstance(composition_plan, CompositionTimelinePlan):
        raise ProjectMotionProductionError("composition_plan must be a CompositionTimelinePlan")
    if composition_plan.project_id != project.id:
        raise ProjectMotionProductionError("composition timeline belongs to another project")
    if not composition_plan.is_valid:
        raise ProjectMotionProductionError("composition timeline contains blocking diagnostics")

    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise ProjectMotionProductionError("Universal project data is read-only")
    stored = state.extra.get(SCENE_COMPOSITIONS_KEY, {})
    if not isinstance(stored, dict):
        raise ProjectMotionProductionError("stored scene compositions are malformed")

    motions = []
    for slot in sorted(
        composition_plan.slots,
        key=lambda item: (item.frame_start, item.scene_order, item.scene_id),
    ):
        entry = stored.get(slot.scene_id)
        if not isinstance(entry, dict):
            raise ProjectMotionProductionError(
                f"scene {slot.scene_id!r} has no persisted composition"
            )
        version = entry.get("storage_version", SCENE_COMPOSITION_STORAGE_VERSION)
        raw = entry.get("composition")
        if version != SCENE_COMPOSITION_STORAGE_VERSION or not isinstance(raw, dict):
            raise ProjectMotionProductionError(
                f"scene {slot.scene_id!r} composition is unsupported or malformed"
            )
        try:
            composition = SceneComposition.from_dict(raw)
        except (TypeError, ValueError) as exc:
            raise ProjectMotionProductionError(
                f"scene {slot.scene_id!r} composition is invalid: {exc}"
            ) from exc
        if (
            composition.scene_id != slot.scene_id
            or composition.fingerprint != slot.composition_fingerprint
        ):
            raise ProjectMotionProductionError(
                f"scene {slot.scene_id!r} composition changed after timeline planning"
            )
        preview = preview_scene_composition(project, composition)
        if (
            not preview.is_valid
            or preview.target_fingerprint != slot.composition_target_fingerprint
        ):
            raise ProjectMotionProductionError(
                f"scene {slot.scene_id!r} composition bindings are invalid or stale"
            )
        duration_frames = slot.segment_frame_end - slot.frame_start
        if duration_frames <= 0:
            raise ProjectMotionProductionError(
                f"scene {slot.scene_id!r} has an empty motion frame interval"
            )
        preset = AUTOMATIC_MOTION_PRESETS[slot.scene_order % len(AUTOMATIC_MOTION_PRESETS)]
        motions.append((slot.scene_id, _scene_motion(slot.scene_id, duration_frames, preset)))

    scene_motions = dict(motions)
    try:
        motion_plan = build_project_motion_timeline_plan(
            project, composition_plan, scene_motions,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectMotionProductionError(
            f"could not bind automatic motion to the saved transition settings: {exc}"
        ) from exc
    return AutomaticMotionPlan(
        project_id=project.id,
        composition_plan_fingerprint=composition_plan.plan_fingerprint,
        scene_motions=tuple(motions),
        motion_plan=motion_plan,
    )


def build_project_motion_production_plan(
    project: Project,
    narration_duration_ticks: Mapping[str, int],
    *,
    narration_pause_ticks: Optional[Mapping[str, int]] = None,
) -> ProjectMotionProductionPlan:
    """Build the complete immutable project/timing/motion plan without rendering."""
    try:
        composition_plan = build_composition_timeline_plan(
            project, narration_duration_ticks,
            narration_pause_ticks=narration_pause_ticks,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectMotionProductionError(f"could not build the composition timeline: {exc}") from exc
    if not composition_plan.is_valid:
        blocking = [
            item.message for item in composition_plan.diagnostics
            if item.severity == "error"
        ]
        raise ProjectMotionProductionError(
            "project is not ready for Universal Produce: " + "; ".join(blocking)
        )
    automatic = build_automatic_motion_plan(project, composition_plan)
    return ProjectMotionProductionPlan(composition_plan, automatic)


def assemble_aligned_narration_wav(
    composition_plan: CompositionTimelinePlan,
    scene_audio_paths: Mapping[str, Path],
    narration_duration_ticks: Mapping[str, int],
    destination: Path,
    *,
    sample_rate: int = constants.NARRATION_SAMPLE_RATE,
) -> Path:
    """Build one exact timeline-aligned WAV from the generated per-scene WAVs.

    Each scene receives silence up to its approved timeline slot, including
    configured-duration padding and the final scene tail. Scenes without
    narration are represented by digital silence. The result is padded to at
    least the frame-quantized output duration required by the MP4 muxer.
    """
    if not isinstance(composition_plan, CompositionTimelinePlan) or not composition_plan.is_valid:
        raise ProjectMotionProductionError("a valid composition timeline is required")
    if not isinstance(scene_audio_paths, Mapping) or not isinstance(narration_duration_ticks, Mapping):
        raise ProjectMotionProductionError("scene audio paths and narration durations must be mappings")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ProjectMotionProductionError("sample_rate must be a positive integer")

    slots = tuple(sorted(
        composition_plan.slots,
        key=lambda item: (item.frame_start, item.scene_order, item.scene_id),
    ))
    expected_ids = {slot.scene_id for slot in slots}
    unknown_audio = sorted(set(scene_audio_paths) - expected_ids)
    unknown_durations = sorted(set(narration_duration_ticks) - expected_ids)
    if unknown_audio or unknown_durations:
        raise ProjectMotionProductionError(
            "audio inputs reference unknown scenes: " + ", ".join(unknown_audio + unknown_durations)
        )

    target = Path(destination).expanduser()
    if target.suffix.lower() != ".wav":
        raise ProjectMotionProductionError("aligned narration destination must use .wav")
    if target.is_symlink() or target.exists():
        raise ProjectMotionProductionError("aligned narration destination already exists or is a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with WavBuilder(target, sample_rate) as builder:
            for slot in slots:
                scene_id = slot.scene_id
                source_value = scene_audio_paths.get(scene_id)
                measured_ticks = narration_duration_ticks.get(scene_id)
                if source_value is None:
                    if measured_ticks is not None or slot.narration_duration_ticks is not None:
                        raise ProjectMotionProductionError(
                            f"scene {scene_id!r} has narration timing but no scene WAV"
                        )
                    builder.add_silence_ticks(slot.slot_ticks)
                    continue
                if measured_ticks is None or slot.narration_duration_ticks != measured_ticks:
                    raise ProjectMotionProductionError(
                        f"scene {scene_id!r} narration duration does not match the approved timeline"
                    )
                source = Path(source_value).expanduser()
                if source.is_symlink() or not source.is_file():
                    raise ProjectMotionProductionError(
                        f"scene {scene_id!r} narration WAV is missing or not a regular file"
                    )
                actual_ticks = wav_duration_ticks(source)
                if actual_ticks != measured_ticks:
                    raise ProjectMotionProductionError(
                        f"scene {scene_id!r} narration WAV duration changed after planning"
                    )
                if actual_ticks > slot.slot_ticks:
                    raise ProjectMotionProductionError(
                        f"scene {scene_id!r} narration is longer than its approved timeline slot"
                    )
                builder.add_wav(source)
                builder.add_silence_ticks(slot.slot_ticks - actual_ticks)

            required_ticks = frames_to_ticks(
                composition_plan.total_frames, composition_plan.fps, rounding="ceil",
            )
            required_samples = ticks_to_samples(required_ticks, sample_rate, rounding="ceil")
            if builder.frames < required_samples:
                builder.add_silence_samples(required_samples - builder.frames)
    except ProjectMotionProductionError:
        target.unlink(missing_ok=True)
        raise
    except (OSError, ValueError) as exc:
        target.unlink(missing_ok=True)
        raise ProjectMotionProductionError(f"could not assemble aligned narration WAV: {exc}") from exc
    return target


def render_project_motion_production(
    project: Project,
    plan: ProjectMotionProductionPlan,
    scene_audio_paths: Mapping[str, Path],
    narration_duration_ticks: Mapping[str, int],
    destination: Path,
    ffmpeg: FFmpegTool,
    asset_library: VisualAssetLibrary,
    *,
    narration_pause_ticks: Optional[Mapping[str, int]] = None,
    cancel: Optional[CancelToken] = None,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> MotionTimelineRenderResult:
    """Render the approved project plan into one validated motion MP4."""
    if not isinstance(plan, ProjectMotionProductionPlan):
        raise ProjectMotionProductionError("plan must be a ProjectMotionProductionPlan")
    if plan.composition_plan.project_id != project.id or plan.automatic_motion.project_id != project.id:
        raise ProjectMotionProductionError("production plan belongs to another project")
    if (
        plan.automatic_motion.composition_plan_fingerprint
        != plan.composition_plan.plan_fingerprint
    ):
        raise ProjectMotionProductionError("automatic motion plan is stale")
    target = Path(destination).expanduser()
    if target.suffix.lower() != ".mp4":
        raise ProjectMotionProductionError("destination must use the .mp4 extension")
    if target.is_symlink() or target.exists():
        raise ProjectMotionProductionError("destination already exists or is a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(
            prefix=".voxora-universal-produce-", dir=str(target.parent)
        ) as temporary:
            narration_path = Path(temporary) / "aligned-narration.wav"
            assemble_aligned_narration_wav(
                plan.composition_plan, scene_audio_paths,
                narration_duration_ticks, narration_path,
            )
            coordinator = MotionTimelineRenderCoordinator(ffmpeg, asset_library)
            return coordinator.run(
                project,
                plan.composition_plan,
                plan.motion_plan,
                plan.scene_motions,
                narration_path,
                narration_duration_ticks,
                target,
                narration_pause_ticks=narration_pause_ticks,
                cancel=cancel,
                on_progress=on_progress,
            )
    except ProjectMotionProductionError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise ProjectMotionProductionError(f"Universal Produce failed: {exc}") from exc


__all__ = [
    "AUTOMATIC_MOTION_PRESETS",
    "AUTOMATIC_MOTION_VERSION",
    "AutomaticMotionPlan",
    "ProjectMotionProductionError",
    "ProjectMotionProductionPlan",
    "assemble_aligned_narration_wav",
    "build_automatic_motion_plan",
    "build_project_motion_production_plan",
    "render_project_motion_production",
]
