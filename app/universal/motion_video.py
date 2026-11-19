"""End-to-end motion frame sequence to silent MP4 rendering.

This opt-in coordinator joins the motion-aware raster renderer to the existing
validated FFmpeg frame-sequence encoder. It does not persist motion or modify
the legacy ProductionJob/audio pipeline.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

from app.universal.composition import SceneComposition
from app.universal.frame_sequence import (
    FFmpegFrameSequenceEncoder,
    FrameSequence,
    FrameSequenceCancelledError,
    FrameSequenceEncodeResult,
    FrameSequenceError,
)
from app.universal.motion import SceneMotion
from app.universal.motion_raster_renderer import (
    MotionRasterRenderCancelledError,
    MotionRasterRenderError,
    MotionRasterRenderer,
)


class MotionVideoRenderError(RuntimeError):
    """Raised when a motion-to-video render cannot complete safely."""


class MotionVideoRenderCancelledError(MotionVideoRenderError):
    """Raised when motion frame rendering or MP4 encoding is cancelled."""


@dataclass(frozen=True)
class MotionVideoRenderResult:
    destination: Path
    frame_count: int
    fps: int
    width: int
    height: int
    duration_seconds: float
    output_sha256: str
    codec: str


def _render_cancel_signal(cancel):
    """Adapt CancelToken's cancelled property to the raster renderer contract."""
    if cancel is None or isinstance(cancel, bool):
        return cancel
    if callable(getattr(cancel, "is_set", None)) or callable(cancel):
        return cancel
    if hasattr(cancel, "cancelled"):
        return lambda: bool(cancel.cancelled)
    raise MotionVideoRenderError(
        "cancel must be a boolean, callable, event-like object, or CancelToken"
    )


class MotionVideoRenderCoordinator:
    """Render motion frames sequentially and encode them as a verified MP4.

    The output is silent. Audio muxing and timeline orchestration remain
    separate, explicit workflow stages.
    """

    def __init__(
        self,
        *,
        motion_renderer: Optional[MotionRasterRenderer] = None,
        encoder: Optional[FFmpegFrameSequenceEncoder] = None,
    ) -> None:
        self._renderer = motion_renderer or MotionRasterRenderer()
        self._encoder = encoder or FFmpegFrameSequenceEncoder()
        if not isinstance(self._renderer, MotionRasterRenderer):
            raise TypeError("motion_renderer must be a MotionRasterRenderer")
        if not isinstance(self._encoder, FFmpegFrameSequenceEncoder):
            raise TypeError("encoder must be an FFmpegFrameSequenceEncoder")

    def run(
        self,
        composition: SceneComposition,
        motion: SceneMotion,
        *,
        asset_paths: Mapping[str, os.PathLike[str] | str],
        destination: os.PathLike[str] | str,
        fps: int,
        cancel=None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> MotionVideoRenderResult:
        if not isinstance(composition, SceneComposition):
            raise MotionVideoRenderError("composition must be a SceneComposition")
        if not isinstance(motion, SceneMotion):
            raise MotionVideoRenderError("motion must be a SceneMotion")
        if composition.scene_id != motion.scene_id:
            raise MotionVideoRenderError("motion and composition scene IDs do not match")
        if not isinstance(asset_paths, Mapping):
            raise MotionVideoRenderError("asset_paths must be a mapping")
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 120:
            raise MotionVideoRenderError("fps must be an integer between 1 and 120")
        if on_progress is not None and not callable(on_progress):
            raise MotionVideoRenderError("on_progress must be callable")

        target = Path(destination).expanduser()
        if target.suffix.lower() != ".mp4":
            raise MotionVideoRenderError("destination must use the .mp4 extension")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise MotionVideoRenderError("destination must be a regular file, not a symlink")
        if target.exists():
            raise MotionVideoRenderError(
                "destination already exists; explicit overwrite is not supported"
            )
        target.parent.mkdir(parents=True, exist_ok=True)

        render_cancel = _render_cancel_signal(cancel)

        def report_render(fraction: float, message: str) -> None:
            if on_progress:
                on_progress(max(0.0, min(0.7, fraction * 0.7)), message)

        def report_encode(fraction: float) -> None:
            if on_progress:
                on_progress(0.7 + max(0.0, min(1.0, fraction)) * 0.3,
                            "Encoding and verifying MP4")

        try:
            if render_cancel is not None:
                cancelled = (
                    render_cancel if isinstance(render_cancel, bool)
                    else bool(render_cancel.is_set()) if callable(getattr(render_cancel, "is_set", None))
                    else bool(render_cancel())
                )
                if cancelled:
                    raise MotionVideoRenderCancelledError("motion video rendering was cancelled")

            # Keep all intermediate frames private and remove them on every exit.
            with tempfile.TemporaryDirectory(
                prefix=".voxora-motion-video-", dir=str(target.parent)
            ) as temporary:
                frame_dir = Path(temporary) / "frames"
                rendered = self._renderer.render_sequence(
                    composition,
                    motion,
                    asset_paths=asset_paths,
                    destination_dir=frame_dir,
                    on_progress=report_render,
                    cancel=render_cancel,
                )
                sequence = FrameSequence.from_paths(rendered.frame_paths, fps=fps)
                encoded: FrameSequenceEncodeResult = self._encoder.encode(
                    sequence,
                    target,
                    on_progress=report_encode,
                    cancel=cancel,
                )

            if on_progress:
                on_progress(1.0, "Motion MP4 render complete")
            return MotionVideoRenderResult(
                destination=encoded.destination,
                frame_count=encoded.frame_count,
                fps=encoded.fps,
                width=encoded.width,
                height=encoded.height,
                duration_seconds=encoded.duration_seconds,
                output_sha256=encoded.output_sha256,
                codec=encoded.codec,
            )
        except (MotionRasterRenderCancelledError, FrameSequenceCancelledError) as exc:
            raise MotionVideoRenderCancelledError(str(exc)) from exc
        except (MotionRasterRenderError, FrameSequenceError, OSError, ValueError) as exc:
            if isinstance(exc, MotionVideoRenderError):
                raise
            raise MotionVideoRenderError(f"motion MP4 render failed: {exc}") from exc


__all__ = [
    "MotionVideoRenderCancelledError",
    "MotionVideoRenderCoordinator",
    "MotionVideoRenderError",
    "MotionVideoRenderResult",
]
