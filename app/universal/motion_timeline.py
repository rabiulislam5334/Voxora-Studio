"""Timeline-aware multi-scene motion rendering for Universal projects.

This opt-in pipeline combines approved scene compositions, per-scene motion,
the immutable composition timeline, the existing frame-sequence encoder, and
the existing Studio audio mixer/muxer. Motion remains caller-supplied until a
separate persistence/editor phase is implemented.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

from PIL import Image

from app.audio.ffmpeg_tool import FFmpegTool
from app.studio.models import StudioState
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import SceneComposition
from app.universal.composition_audio_mux import (
    CompositionAudioMuxResult,
    CompositionAudioMuxer,
)
from app.universal.composition_timeline import (
    CompositionTimelinePlan,
    StaleCompositionTimelinePlanError,
    assert_composition_timeline_plan_current,
)
from app.universal.composition_workflow import (
    SCENE_COMPOSITIONS_KEY,
    SCENE_COMPOSITION_STORAGE_VERSION,
    preview_scene_composition,
)
from app.universal.frame_sequence import (
    FFmpegFrameSequenceEncoder,
    FrameSequence,
    FrameSequenceCancelledError,
    FrameSequenceError,
)
from app.universal.models import UniversalState
from app.universal.motion import SceneMotion
from app.universal.motion_raster_renderer import (
    MotionRasterRenderCancelledError,
    MotionRasterRenderError,
    MotionRasterRenderer,
)
from app.universal.raster_renderer import resolve_scene_composition_assets
from app.workers.cancel import CancelToken


class MotionTimelinePlanError(ValueError):
    """Raised when scene motion cannot be aligned to the approved timeline."""


class MotionTimelineRenderError(RuntimeError):
    """Raised when multi-scene motion rendering cannot complete safely."""


class MotionTimelineRenderCancelledError(MotionTimelineRenderError):
    """Raised when a multi-scene motion render is cancelled."""


@dataclass(frozen=True)
class MotionSceneTimelineSlot:
    scene_id: str
    scene_order: int
    frame_start: int
    frame_end: int
    segment_frame_end: int
    motion: SceneMotion

    @property
    def frame_count(self) -> int:
        """Number of rendered source frames, including any outgoing overlap."""
        return self.segment_frame_end - self.frame_start


@dataclass(frozen=True)
class MotionTimelinePlan:
    composition_plan_fingerprint: str
    fps: int
    total_frames: int
    transition: str
    transition_frames: int
    scenes: tuple[MotionSceneTimelineSlot, ...]
    motion_fingerprint: str
    plan_fingerprint: str


@dataclass(frozen=True)
class MotionTimelineRenderResult:
    destination: Path
    scene_count: int
    frame_count: int
    fps: int
    duration_seconds: float
    audio: CompositionAudioMuxResult


def _digest(payload: object) -> str:
    try:
        raw = json.dumps(
            payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MotionTimelinePlanError(
            f"motion timeline inputs cannot be fingerprinted safely: {exc}"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def build_motion_timeline_plan(
    composition_plan: CompositionTimelinePlan,
    scene_motions: Mapping[str, SceneMotion],
) -> MotionTimelinePlan:
    """Bind one immutable motion definition to each scene's exact frame slot.

    Motion durations must match the already-reviewed composition timeline;
    this builder never stretches, truncates, or silently retimes keyframes.
    """
    if not isinstance(composition_plan, CompositionTimelinePlan):
        raise MotionTimelinePlanError("composition_plan must be a CompositionTimelinePlan")
    if not composition_plan.is_valid:
        raise MotionTimelinePlanError("composition timeline contains blocking diagnostics")
    if composition_plan.transition not in ("cut", "crossfade"):
        raise MotionTimelinePlanError(
            f"unsupported transition type: {composition_plan.transition!r}"
        )
    if composition_plan.transition == "cut" and composition_plan.transition_ticks != 0:
        raise MotionTimelinePlanError("cut transitions must have zero transition duration")
    if composition_plan.transition == "crossfade" and composition_plan.transition_ticks <= 0:
        raise MotionTimelinePlanError("crossfade transitions require a positive duration")
    if not isinstance(scene_motions, Mapping):
        raise MotionTimelinePlanError("scene_motions must map scene IDs to SceneMotion values")
    if not composition_plan.slots:
        raise MotionTimelinePlanError("composition timeline contains no scenes")
    if (
        isinstance(composition_plan.total_frames, bool)
        or not isinstance(composition_plan.total_frames, int)
        or composition_plan.total_frames <= 0
    ):
        raise MotionTimelinePlanError("composition timeline must contain output frames")

    ordered_slots = tuple(sorted(
        composition_plan.slots, key=lambda item: (item.frame_start, item.scene_order, item.scene_id)
    ))
    expected_ids = {slot.scene_id for slot in ordered_slots}
    supplied_ids = set(scene_motions)
    if any(not isinstance(scene_id, str) or not scene_id.strip() for scene_id in supplied_ids):
        raise MotionTimelinePlanError("scene_motions contains an invalid scene ID")
    missing = sorted(expected_ids - supplied_ids)
    unknown = sorted(supplied_ids - expected_ids)
    if missing:
        raise MotionTimelinePlanError("missing motion definitions for scenes: " + ", ".join(missing))
    if unknown:
        raise MotionTimelinePlanError("motion definitions reference unknown scenes: " + ", ".join(unknown))

    cursor = 0
    scene_slots = []
    motion_payload = []
    overlap_frames = []
    for index, slot in enumerate(ordered_slots):
        if slot.frame_start != cursor or slot.frame_end <= slot.frame_start:
            raise MotionTimelinePlanError(
                "scene frame intervals must be contiguous, ordered, and non-empty"
            )
        if slot.segment_frame_end < slot.frame_end:
            raise MotionTimelinePlanError(
                f"scene {slot.scene_id!r} segment ends before its timeline slot"
            )
        if slot.segment_frame_end > composition_plan.total_frames:
            raise MotionTimelinePlanError(
                f"scene {slot.scene_id!r} segment extends beyond the output timeline"
            )
        overlap = slot.segment_frame_end - slot.frame_end
        if index == len(ordered_slots) - 1 and overlap:
            raise MotionTimelinePlanError("the final scene cannot have an outgoing transition overlap")
        overlap_frames.append(overlap)
        if slot.composition_fingerprint is None or slot.composition_target_fingerprint is None:
            raise MotionTimelinePlanError(
                f"scene {slot.scene_id!r} has no validated composition snapshot"
            )
        motion = scene_motions[slot.scene_id]
        if not isinstance(motion, SceneMotion):
            raise MotionTimelinePlanError(
                f"motion for scene {slot.scene_id!r} must be a SceneMotion"
            )
        if motion.scene_id != slot.scene_id:
            raise MotionTimelinePlanError(
                f"motion scene ID does not match timeline scene {slot.scene_id!r}"
            )
        expected_frames = slot.segment_frame_end - slot.frame_start
        if motion.duration_frames != expected_frames:
            raise MotionTimelinePlanError(
                f"motion for scene {slot.scene_id!r} has {motion.duration_frames} frames; "
                f"timeline requires exactly {expected_frames}"
            )
        scene_slots.append(MotionSceneTimelineSlot(
            scene_id=slot.scene_id,
            scene_order=slot.scene_order,
            frame_start=slot.frame_start,
            frame_end=slot.frame_end,
            segment_frame_end=slot.segment_frame_end,
            motion=motion,
        ))
        motion_payload.append({
            "scene_id": slot.scene_id,
            "motion": motion.to_dict(),
            "frame_start": slot.frame_start,
            "frame_end": slot.frame_end,
            "segment_frame_end": slot.segment_frame_end,
        })
        cursor = slot.frame_end

    if cursor != composition_plan.total_frames:
        raise MotionTimelinePlanError(
            "scene motion intervals do not cover the complete composition timeline"
        )
    if composition_plan.transition == "cut":
        if any(overlap_frames):
            raise MotionTimelinePlanError("cut transitions cannot contain overlapping scene frames")
        transition_frames = 0
    else:
        if len(ordered_slots) < 2:
            raise MotionTimelinePlanError("crossfade requires at least two scenes")
        if not overlap_frames or any(value <= 0 for value in overlap_frames[:-1]):
            raise MotionTimelinePlanError(
                "crossfade is shorter than one output frame at the selected FPS"
            )
        if len(set(overlap_frames[:-1])) != 1 or overlap_frames[-1] != 0:
            raise MotionTimelinePlanError(
                "all outgoing scene overlaps must use the same frame duration"
            )
        transition_frames = overlap_frames[0]
        if any(
            ordered_slots[index].segment_frame_end > ordered_slots[index + 1].frame_end
            for index in range(len(ordered_slots) - 1)
        ):
            raise MotionTimelinePlanError("crossfade overlaps cannot span more than adjacent scenes")

    motion_fingerprint = _digest(motion_payload)
    payload = {
        "composition_plan_fingerprint": composition_plan.plan_fingerprint,
        "fps": composition_plan.fps,
        "total_frames": composition_plan.total_frames,
        "transition": composition_plan.transition,
        "transition_frames": transition_frames,
        "motion_fingerprint": motion_fingerprint,
        "scenes": [
            {
                "scene_id": item.scene_id,
                "scene_order": item.scene_order,
                "frame_start": item.frame_start,
                "frame_end": item.frame_end,
            }
            for item in scene_slots
        ],
    }
    return MotionTimelinePlan(
        composition_plan_fingerprint=composition_plan.plan_fingerprint,
        fps=composition_plan.fps,
        total_frames=composition_plan.total_frames,
        transition=composition_plan.transition,
        transition_frames=transition_frames,
        scenes=tuple(scene_slots),
        motion_fingerprint=motion_fingerprint,
        plan_fingerprint=_digest(payload),
    )


def assert_motion_timeline_plan_current(
    composition_plan: CompositionTimelinePlan,
    scene_motions: Mapping[str, SceneMotion],
    plan: MotionTimelinePlan,
) -> None:
    """Reject stale or modified motion inputs before and during rendering."""
    if not isinstance(plan, MotionTimelinePlan):
        raise MotionTimelinePlanError("plan must be a MotionTimelinePlan")
    current = build_motion_timeline_plan(composition_plan, scene_motions)
    if current != plan:
        raise MotionTimelinePlanError(
            "motion timeline plan is stale; rebuild and review it before rendering"
        )


def _cancel(cancel: Optional[CancelToken]) -> None:
    if cancel is not None:
        cancel.raise_if_cancelled("Motion timeline render cancelled.")


def _save_normalized_frame(
    source: Path,
    destination: Path,
    width: int,
    height: int,
) -> None:
    """Save a frame on the output canvas without changing its aspect ratio policy."""
    with Image.open(source) as image:
        frame = image.convert("RGBA")
        try:
            if frame.size != (width, height):
                resized = frame.resize(
                    (width, height), resample=Image.Resampling.LANCZOS,
                )
                try:
                    resized.save(destination, format="PNG", optimize=False)
                finally:
                    resized.close()
            else:
                frame.save(destination, format="PNG", optimize=False)
        finally:
            frame.close()


class MotionTimelineRenderCoordinator:
    """Render all animated scenes into one verified MP4 with aligned audio.

    The caller must obtain explicit approval for both immutable plans before
    invoking run(). Scene motion is supplied explicitly; it is not persisted
    to project files and no legacy ProductionJob path is changed.
    """

    def __init__(
        self,
        ffmpeg: FFmpegTool,
        asset_library: VisualAssetLibrary,
        *,
        motion_renderer: Optional[MotionRasterRenderer] = None,
        encoder: Optional[FFmpegFrameSequenceEncoder] = None,
    ) -> None:
        if not isinstance(ffmpeg, FFmpegTool):
            raise TypeError("ffmpeg must be an FFmpegTool")
        if not isinstance(asset_library, VisualAssetLibrary):
            raise TypeError("asset_library must be a VisualAssetLibrary")
        self._ffmpeg = ffmpeg
        self._library = asset_library
        self._renderer = motion_renderer or MotionRasterRenderer()
        self._encoder = encoder or FFmpegFrameSequenceEncoder()
        if not isinstance(self._renderer, MotionRasterRenderer):
            raise TypeError("motion_renderer must be a MotionRasterRenderer")
        if not isinstance(self._encoder, FFmpegFrameSequenceEncoder):
            raise TypeError("encoder must be an FFmpegFrameSequenceEncoder")
        self._muxer = CompositionAudioMuxer(ffmpeg)

    def run(
        self,
        project,
        composition_plan: CompositionTimelinePlan,
        motion_plan: MotionTimelinePlan,
        scene_motions: Mapping[str, SceneMotion],
        narration_wav: os.PathLike[str] | str,
        narration_duration_ticks: Mapping[str, int],
        destination: os.PathLike[str] | str,
        *,
        narration_pause_ticks: Optional[Mapping[str, int]] = None,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> MotionTimelineRenderResult:
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable")
        if motion_plan.transition != composition_plan.transition:
            raise MotionTimelineRenderError("motion plan transition does not match composition timeline")
        if motion_plan.transition_frames < 0:
            raise MotionTimelineRenderError("motion plan transition frame count is invalid")
        if not composition_plan.is_valid:
            raise MotionTimelineRenderError("composition timeline contains blocking diagnostics")
        if not isinstance(cancel, (CancelToken, type(None))):
            raise TypeError("cancel must be a CancelToken or None")

        target = Path(destination).expanduser()
        if target.suffix.lower() != ".mp4":
            raise MotionTimelineRenderError("destination must use the .mp4 extension")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise MotionTimelineRenderError("destination must be a regular file, not a symlink")
        if target.exists():
            raise MotionTimelineRenderError("destination already exists; refusing to overwrite it")
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            assert_composition_timeline_plan_current(
                project, composition_plan, narration_duration_ticks,
                narration_pause_ticks=narration_pause_ticks,
            )
            assert_motion_timeline_plan_current(composition_plan, scene_motions, motion_plan)
            _cancel(cancel)
            universal = UniversalState.from_project_settings(project.settings)
            studio = StudioState.from_project_settings(project.settings)
            if universal.read_only or studio.read_only:
                raise MotionTimelineRenderError(
                    "project Universal or Studio settings are read-only"
                )
            stored = universal.extra.get(SCENE_COMPOSITIONS_KEY, {})
            if not isinstance(stored, dict):
                raise MotionTimelineRenderError("stored scene compositions are malformed")

            cursor = 0
            for index, slot in enumerate(motion_plan.scenes):
                if slot.frame_start != cursor or slot.frame_end <= slot.frame_start:
                    raise MotionTimelineRenderError(
                        "motion scene frame intervals are not contiguous and non-empty"
                    )
                if slot.segment_frame_end < slot.frame_end:
                    raise MotionTimelineRenderError("motion scene segment ends before its timeline slot")
                if index == len(motion_plan.scenes) - 1 and slot.segment_frame_end != slot.frame_end:
                    raise MotionTimelineRenderError("final scene cannot have an outgoing overlap")
                cursor = slot.frame_end
            if cursor != composition_plan.total_frames:
                raise MotionTimelineRenderError(
                    "motion scene intervals do not cover the complete output timeline"
                )

            with tempfile.TemporaryDirectory(
                prefix=".voxora-motion-timeline-", dir=str(target.parent)
            ) as temporary:
                work = Path(temporary)
                frame_dir = work / "frames"
                frame_dir.mkdir()
                frame_paths: list[Path] = []
                scene_frame_paths: dict[str, tuple[Path, ...]] = {}
                rendered_before = 0
                total_scene_frames = sum(item.frame_count for item in motion_plan.scenes)
                for index, slot in enumerate(motion_plan.scenes):
                    _cancel(cancel)
                    entry = stored.get(slot.scene_id)
                    if not isinstance(entry, dict):
                        raise MotionTimelineRenderError(
                            f"scene {slot.scene_id!r} has no persisted composition"
                        )
                    version = entry.get("storage_version", SCENE_COMPOSITION_STORAGE_VERSION)
                    raw = entry.get("composition")
                    if version != SCENE_COMPOSITION_STORAGE_VERSION or not isinstance(raw, dict):
                        raise MotionTimelineRenderError(
                            f"scene {slot.scene_id!r} composition is unsupported or malformed"
                        )
                    try:
                        composition = SceneComposition.from_dict(raw)
                    except (TypeError, ValueError) as exc:
                        raise MotionTimelineRenderError(
                            f"scene {slot.scene_id!r} composition is invalid: {exc}"
                        ) from exc
                    timeline_slot = next(
                        item for item in composition_plan.slots if item.scene_id == slot.scene_id
                    )
                    if (
                        composition.scene_id != slot.scene_id
                        or composition.fingerprint != timeline_slot.composition_fingerprint
                    ):
                        raise MotionTimelineRenderError(
                            f"scene {slot.scene_id!r} composition changed after timeline planning"
                        )
                    preview = preview_scene_composition(project, composition)
                    if (
                        not preview.is_valid
                        or preview.target_fingerprint != timeline_slot.composition_target_fingerprint
                    ):
                        raise MotionTimelineRenderError(
                            f"scene {slot.scene_id!r} composition bindings are invalid or stale"
                        )
                    asset_paths = resolve_scene_composition_assets(
                        project, composition, self._library,
                    )
                    scene_dir = work / f"scene_{index:05d}"
                    motion = scene_motions[slot.scene_id]

                    def report_scene(fraction: float, message: str, *, base=rendered_before,
                                     count=slot.frame_count, scene_id=slot.scene_id) -> None:
                        if on_progress:
                            value = 0.60 * (base + max(0.0, min(1.0, fraction)) * count) / total_scene_frames
                            on_progress(value, f"{scene_id}: {message}")

                    rendered = self._renderer.render_sequence(
                        composition, motion, asset_paths=asset_paths,
                        destination_dir=scene_dir,
                        on_progress=report_scene,
                        cancel=(lambda: bool(cancel and cancel.cancelled)),
                    )
                    if rendered.frame_count != slot.frame_count:
                        raise MotionTimelineRenderError(
                            f"scene {slot.scene_id!r} rendered an unexpected frame count"
                        )
                    scene_frame_paths[slot.scene_id] = rendered.frame_paths
                    rendered_before += slot.frame_count
                    if on_progress:
                        on_progress(
                            0.60 * rendered_before / total_scene_frames,
                            f"Rendered scene {index + 1}/{len(motion_plan.scenes)}",
                        )

                # Composite each output frame from one active scene or a
                # two-scene alpha blend during the approved overlap interval.
                for output_index in range(motion_plan.total_frames):
                    _cancel(cancel)
                    active = [
                        slot for slot in motion_plan.scenes
                        if slot.frame_start <= output_index < slot.segment_frame_end
                    ]
                    if not active or len(active) > 2:
                        raise MotionTimelineRenderError(
                            f"output frame {output_index} has an invalid active-scene count"
                        )
                    if len(active) == 2:
                        outgoing, incoming = active
                        if outgoing.scene_order >= incoming.scene_order:
                            raise MotionTimelineRenderError("overlapping scenes are not in timeline order")
                        overlap = outgoing.segment_frame_end - incoming.frame_start
                        if overlap != motion_plan.transition_frames or overlap <= 0:
                            raise MotionTimelineRenderError("scene overlap does not match approved transition")
                        if overlap == 1:
                            alpha = 0.5
                        else:
                            alpha = (output_index - incoming.frame_start) / (overlap - 1)
                        first_path = scene_frame_paths[outgoing.scene_id][output_index - outgoing.frame_start]
                        second_path = scene_frame_paths[incoming.scene_id][output_index - incoming.frame_start]
                        with Image.open(first_path) as first_image, Image.open(second_path) as second_image:
                            first = first_image.convert("RGBA")
                            second = second_image.convert("RGBA")
                            try:
                                if first.size != (composition_plan.width, composition_plan.height):
                                    resized = first.resize(
                                        (composition_plan.width, composition_plan.height),
                                        resample=Image.Resampling.LANCZOS,
                                    )
                                    first.close()
                                    first = resized
                                if second.size != (composition_plan.width, composition_plan.height):
                                    resized = second.resize(
                                        (composition_plan.width, composition_plan.height),
                                        resample=Image.Resampling.LANCZOS,
                                    )
                                    second.close()
                                    second = resized
                                composed = Image.blend(first, second, max(0.0, min(1.0, alpha)))
                                try:
                                    output_path = frame_dir / f"frame_{output_index:06d}.png"
                                    composed.save(output_path, format="PNG", optimize=False)
                                finally:
                                    composed.close()
                            finally:
                                first.close()
                                second.close()
                    else:
                        slot = active[0]
                        source_index = output_index - slot.frame_start
                        source = scene_frame_paths[slot.scene_id][source_index]
                        output_path = frame_dir / f"frame_{output_index:06d}.png"
                        _save_normalized_frame(
                            source, output_path, composition_plan.width, composition_plan.height,
                        )
                    frame_paths.append(output_path)
                    if on_progress:
                        on_progress(
                            0.60 + 0.10 * (output_index + 1) / motion_plan.total_frames,
                            f"Compositing frame {output_index + 1}/{motion_plan.total_frames}",
                        )

                _cancel(cancel)
                assert_composition_timeline_plan_current(
                    project, composition_plan, narration_duration_ticks,
                    narration_pause_ticks=narration_pause_ticks,
                )
                assert_motion_timeline_plan_current(composition_plan, scene_motions, motion_plan)
                sequence = FrameSequence.from_paths(tuple(frame_paths), fps=motion_plan.fps)
                silent_video = work / "motion-timeline-silent.mp4"
                encoded = self._encoder.encode(
                    sequence, silent_video,
                    on_progress=lambda fraction: on_progress(
                        0.70 + 0.15 * max(0.0, min(1.0, fraction)),
                        "Encoding full motion timeline",
                    ) if on_progress else None,
                    cancel=cancel,
                )
                if encoded.frame_count != motion_plan.total_frames or encoded.fps != motion_plan.fps:
                    raise MotionTimelineRenderError(
                        "encoded silent MP4 does not match the approved motion timeline"
                    )
                _cancel(cancel)
                assert_composition_timeline_plan_current(
                    project, composition_plan, narration_duration_ticks,
                    narration_pause_ticks=narration_pause_ticks,
                )
                assert_motion_timeline_plan_current(composition_plan, scene_motions, motion_plan)
                audio_result = self._muxer.render(
                    silent_video, Path(narration_wav), studio.audio, target, composition_plan,
                    cancel=cancel,
                    on_progress=lambda fraction, message: on_progress(
                        0.85 + 0.15 * max(0.0, min(1.0, fraction)), message
                    ) if on_progress else None,
                )

            if on_progress:
                on_progress(1.0, "Motion timeline MP4 export complete")
            return MotionTimelineRenderResult(
                destination=audio_result.destination,
                scene_count=len(motion_plan.scenes),
                frame_count=audio_result.frame_count,
                fps=motion_plan.fps,
                duration_seconds=audio_result.duration_seconds,
                audio=audio_result,
            )
        except (MotionRasterRenderCancelledError, FrameSequenceCancelledError) as exc:
            raise MotionTimelineRenderCancelledError(str(exc)) from exc
        except (
            MotionRasterRenderError, FrameSequenceError, StaleCompositionTimelinePlanError,
            OSError, ValueError,
        ) as exc:
            if isinstance(exc, MotionTimelineRenderError):
                raise
            raise MotionTimelineRenderError(f"motion timeline render failed: {exc}") from exc


__all__ = [
    "MotionSceneTimelineSlot",
    "MotionTimelinePlan",
    "MotionTimelinePlanError",
    "MotionTimelineRenderCancelledError",
    "MotionTimelineRenderCoordinator",
    "MotionTimelineRenderError",
    "MotionTimelineRenderResult",
    "assert_motion_timeline_plan_current",
    "build_motion_timeline_plan",
]
