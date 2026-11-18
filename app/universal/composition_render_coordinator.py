"""Opt-in coordinator for still-composition MP4 production.

The coordinator renders one approved composition per scene, builds a compact
FFmpeg concat manifest (rather than duplicating PNGs for every frame), encodes
a silent CFR video, then reuses the existing Studio audio mixer/muxer.

Current boundary: cut transitions only; narration must already be assembled
into one timeline-aligned WAV. This module does not generate TTS or motion.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

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
    assert_composition_timeline_plan_current,
)
from app.universal.composition_workflow import (
    SCENE_COMPOSITIONS_KEY,
    SCENE_COMPOSITION_STORAGE_VERSION,
    preview_scene_composition,
)
from app.universal.models import UniversalState
from app.universal.raster_renderer import (
    RasterCompositionRenderer,
    resolve_scene_composition_assets,
)
from app.workers.cancel import CancelToken


class CompositionRenderCoordinatorError(RuntimeError):
    """Raised when coordinated composition rendering cannot complete safely."""


@dataclass(frozen=True)
class CompositionRenderResult:
    destination: Path
    frame_count: int
    scene_count: int
    fps: int
    duration_seconds: float
    audio: CompositionAudioMuxResult


def _cancel(cancel: Optional[CancelToken]) -> None:
    if cancel is not None:
        cancel.raise_if_cancelled("Composition render cancelled.")


def _quote_concat_path(path: Path) -> str:
    # FFmpeg concat demuxer uses single-quoted paths with backslash escaping.
    value = path.resolve(strict=True).as_posix()
    return "'" + value.replace("\\", "\\\\").replace("'", "'\\''") + "'"


def build_composition_concat_manifest(
    scene_frames: tuple[tuple[Path, int], ...],
    fps: int,
) -> str:
    """Build a concat-demuxer manifest from one still PNG and frame count per scene."""
    if not scene_frames:
        raise CompositionRenderCoordinatorError("at least one rendered scene frame is required")
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
        raise CompositionRenderCoordinatorError("fps must be an integer between 1 and 120")
    lines = ["ffconcat version 1"]
    for path, frames in scene_frames:
        if isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0:
            raise CompositionRenderCoordinatorError("each scene must occupy at least one frame")
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_file() or resolved.suffix.lower() != ".png":
            raise CompositionRenderCoordinatorError("scene frame must be an existing PNG file")
        lines.append(f"file {_quote_concat_path(resolved)}")
        lines.append(f"duration {frames / fps:.12f}")
    # The concat demuxer ignores the final duration unless another file follows.
    lines.append(f"file {_quote_concat_path(Path(scene_frames[-1][0]).resolve(strict=True))}")
    return "\n".join(lines) + "\n"


def build_composition_silent_video_args(
    ffmpeg_executable: Path,
    manifest_path: Path,
    plan: CompositionTimelinePlan,
    destination: Path,
) -> list[str]:
    """Build a CFR H.264 encode command for the compact still-image manifest."""
    if plan.transition != "cut" or plan.transition_ticks != 0:
        raise CompositionRenderCoordinatorError(
            "this coordinator currently supports cut transitions only"
        )
    if not plan.is_valid or plan.total_frames <= 0:
        raise CompositionRenderCoordinatorError("a valid non-empty timeline plan is required")
    return [
        str(ffmpeg_executable), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-y", "-f", "concat", "-safe", "0", "-i", str(manifest_path),
        "-vf", f"scale={plan.width}:{plan.height}:flags=lanczos,setsar=1,format=yuv420p",
        "-fps_mode", "cfr", "-r", str(plan.fps),
        "-frames:v", str(plan.total_frames),
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-movflags", "+faststart", "-f", "mp4", str(destination),
    ]


class CompositionRenderCoordinator:
    """Run the opt-in still-composition → silent MP4 → audio mux workflow.

    The caller must obtain explicit render approval before calling run().
    narration_wav must already contain scene narration and silence aligned to
    the supplied immutable timeline. narration_duration_ticks and
    narration_pause_ticks are the exact inputs used to build that plan.
    """

    def __init__(
        self,
        ffmpeg: FFmpegTool,
        asset_library: VisualAssetLibrary,
        *,
        renderer: Optional[RasterCompositionRenderer] = None,
    ) -> None:
        if not isinstance(ffmpeg, FFmpegTool):
            raise TypeError("ffmpeg must be an FFmpegTool")
        if not isinstance(asset_library, VisualAssetLibrary):
            raise TypeError("asset_library must be a VisualAssetLibrary")
        self._ffmpeg = ffmpeg
        self._library = asset_library
        self._renderer = renderer or RasterCompositionRenderer()
        self._muxer = CompositionAudioMuxer(ffmpeg)

    def run(
        self,
        project,
        plan: CompositionTimelinePlan,
        narration_wav: Path,
        narration_duration_ticks: Mapping[str, int],
        destination: Path,
        *,
        narration_pause_ticks: Optional[Mapping[str, int]] = None,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> CompositionRenderResult:
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable")
        if plan.transition != "cut" or plan.transition_ticks != 0:
            raise CompositionRenderCoordinatorError(
                "crossfade rendering is not implemented yet; select cut transition"
            )
        if not plan.is_valid:
            raise CompositionRenderCoordinatorError("timeline plan contains blocking diagnostics")
        if not plan.slots:
            raise CompositionRenderCoordinatorError("timeline plan contains no scene slots")

        target = Path(destination).expanduser()
        if target.suffix.lower() != ".mp4":
            raise CompositionRenderCoordinatorError("destination must use the .mp4 extension")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise CompositionRenderCoordinatorError("destination must be a regular file, not a symlink")
        if target.exists():
            raise CompositionRenderCoordinatorError("destination already exists; refusing to overwrite it")
        target.parent.mkdir(parents=True, exist_ok=True)

        narration_path = Path(narration_wav).expanduser()
        if narration_path.is_symlink() or not narration_path.is_file():
            raise CompositionRenderCoordinatorError("aligned narration WAV must be a regular file")

        assert_composition_timeline_plan_current(
            project, plan, narration_duration_ticks,
            narration_pause_ticks=narration_pause_ticks,
        )
        state = UniversalState.from_project_settings(project.settings)
        if state.read_only:
            raise CompositionRenderCoordinatorError("Universal project data is read-only")
        stored = state.extra.get(SCENE_COMPOSITIONS_KEY, {})
        if not isinstance(stored, dict):
            raise CompositionRenderCoordinatorError("stored scene compositions are malformed")
        studio = StudioState.from_project_settings(project.settings)
        if studio.read_only:
            raise CompositionRenderCoordinatorError("Studio audio settings are malformed or read-only")

        # Validate exact frame coverage before allocating any render artifacts.
        cursor = 0
        for slot in plan.slots:
            if slot.frame_start != cursor or slot.frame_end <= slot.frame_start:
                raise CompositionRenderCoordinatorError(
                    "cut timeline scene frame intervals must be contiguous and non-empty"
                )
            cursor = slot.frame_end
        if cursor != plan.total_frames:
            raise CompositionRenderCoordinatorError(
                "scene frame intervals do not cover the complete output timeline"
            )

        with tempfile.TemporaryDirectory(
            prefix=".voxora-composition-", dir=str(target.parent)
        ) as temporary:
            work = Path(temporary)
            scene_frames: list[tuple[Path, int]] = []
            total_scenes = len(plan.slots)
            for index, slot in enumerate(plan.slots):
                _cancel(cancel)
                entry = stored.get(slot.scene_id)
                if not isinstance(entry, dict):
                    raise CompositionRenderCoordinatorError(
                        f"scene {slot.scene_id!r} has no persisted composition"
                    )
                version = entry.get("storage_version", SCENE_COMPOSITION_STORAGE_VERSION)
                raw = entry.get("composition")
                if version != SCENE_COMPOSITION_STORAGE_VERSION or not isinstance(raw, dict):
                    raise CompositionRenderCoordinatorError(
                        f"scene {slot.scene_id!r} has an unsupported or malformed composition"
                    )
                try:
                    composition = SceneComposition.from_dict(raw)
                except (TypeError, ValueError) as exc:
                    raise CompositionRenderCoordinatorError(
                        f"scene {slot.scene_id!r} composition is invalid: {exc}"
                    ) from exc
                if (
                    composition.scene_id != slot.scene_id
                    or composition.fingerprint != slot.composition_fingerprint
                ):
                    raise CompositionRenderCoordinatorError(
                        f"scene {slot.scene_id!r} composition changed after timeline planning"
                    )
                preview = preview_scene_composition(project, composition)
                if (
                    not preview.is_valid
                    or preview.target_fingerprint != slot.composition_target_fingerprint
                ):
                    raise CompositionRenderCoordinatorError(
                        f"scene {slot.scene_id!r} composition bindings are invalid or stale"
                    )
                asset_paths = resolve_scene_composition_assets(
                    project, composition, self._library,
                )
                frame_path = work / f"scene_{index:06d}.png"
                self._renderer.render(
                    composition, asset_paths=asset_paths, destination=frame_path,
                    cancel=cancel,
                )
                scene_frames.append((frame_path, slot.frame_end - slot.frame_start))
                if on_progress:
                    on_progress(0.35 * (index + 1) / total_scenes,
                                 f"Rendered scene {index + 1}/{total_scenes}")

            _cancel(cancel)
            assert_composition_timeline_plan_current(
                project, plan, narration_duration_ticks,
                narration_pause_ticks=narration_pause_ticks,
            )
            manifest = work / "frames.ffconcat"
            manifest.write_text(
                build_composition_concat_manifest(tuple(scene_frames), plan.fps),
                encoding="utf-8",
                newline="\n",
            )
            silent_video = work / "silent.mp4"
            args = build_composition_silent_video_args(
                self._ffmpeg.require(), manifest, plan, silent_video,
            )
            duration_s = plan.total_frames / plan.fps
            self._ffmpeg.run_with_progress(
                args, duration_s,
                lambda fraction: on_progress(0.35 + 0.30 * fraction, "Encoding silent video")
                if on_progress else None,
                cancel,
            )
            if not silent_video.is_file() or silent_video.stat().st_size <= 0:
                raise CompositionRenderCoordinatorError("FFmpeg did not produce the silent MP4")

            _cancel(cancel)
            assert_composition_timeline_plan_current(
                project, plan, narration_duration_ticks,
                narration_pause_ticks=narration_pause_ticks,
            )
            audio_result = self._muxer.render(
                silent_video, narration_path, studio.audio, target, plan,
                cancel=cancel,
                on_progress=lambda fraction, message: on_progress(
                    0.65 + 0.35 * fraction, message
                ) if on_progress else None,
            )
            if on_progress:
                on_progress(1.0, "Composition video export complete")
            return CompositionRenderResult(
                destination=audio_result.destination,
                frame_count=plan.total_frames,
                scene_count=total_scenes,
                fps=plan.fps,
                duration_seconds=audio_result.duration_seconds,
                audio=audio_result,
            )
