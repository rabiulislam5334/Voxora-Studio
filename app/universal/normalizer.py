"""Normalize renderer outputs to Voxora's shared silent MP4 segment contract.

This module is deliberately separate from scene rendering. Engines may render
in their own native format, then pass the result here before it enters the
shared segment cache/join pipeline.
"""
from __future__ import annotations

import math
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core import constants
from app.core.exceptions import MediaError
from app.workers.cancel import CancelToken


@dataclass(frozen=True)
class SegmentOutputSpec:
    """Required properties of a normalized timeline segment."""

    duration_s: float
    width: int
    height: int
    fps: int

    def __post_init__(self) -> None:
        if isinstance(self.duration_s, bool) or not isinstance(self.duration_s, (int, float)):
            raise ValueError("duration_s must be a positive finite number")
        try:
            finite = math.isfinite(float(self.duration_s))
        except (OverflowError, ValueError):
            finite = False
        if not finite or self.duration_s <= 0:
            raise ValueError("duration_s must be a positive finite number")
        for name in ("width", "height", "fps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.width % 2 or self.height % 2:
            raise ValueError("width and height must be even for the shared yuv420p output")


@dataclass(frozen=True)
class NormalizedSegment:
    """Verified output artifact accepted by the shared video pipeline.

    The contract guarantees MP4 container, exact dimensions, video presence,
    no audio stream, and duration within the frame-timing tolerance. FPS,
    codec and pixel format are set by the normalizer's encode command; the
    current lightweight FFmpeg probe does not independently inspect them.
    """

    path: Path
    duration_s: float
    width: int
    height: int
    fps: int
    container: str = "mp4"
    has_video: bool = True
    has_audio: bool = False


class SegmentNormalizer:
    """Transcode an engine's raw video into Voxora's shared segment format."""

    def __init__(self, ffmpeg) -> None:
        self._ffmpeg = ffmpeg

    @staticmethod
    def _validate_source(source: Path, destination: Path) -> None:
        if not source.is_file() or source.stat().st_size <= 0:
            raise MediaError(f"Renderer output is missing or empty: {source}")
        if source.resolve() == destination.resolve():
            raise ValueError("source and destination must be different files")
        if destination.suffix.lower() != ".mp4":
            raise ValueError("normalized segment destination must use the .mp4 extension")

    def normalize(
        self,
        source: Path,
        destination: Path,
        spec: SegmentOutputSpec,
        *,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[CancelToken] = None,
    ) -> NormalizedSegment:
        """Create and verify a silent H.264/yuv420p MP4, then atomically publish it."""
        if not isinstance(spec, SegmentOutputSpec):
            raise TypeError("spec must be a SegmentOutputSpec")
        source, destination = Path(source), Path(destination)
        self._validate_source(source, destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f"{destination.stem}.{uuid.uuid4().hex[:8]}.part"
        )
        width, height, fps = spec.width, spec.height, spec.fps
        video_filter = (
            f"fps={fps},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,format=yuv420p"
        )
        args = [
            str(self._ffmpeg.require()), "-hide_banner", "-loglevel", "error",
            "-nostdin", "-y", "-i", str(source), "-map", "0:v:0",
            "-vf", video_filter, "-an", "-sn", "-dn",
            "-c:v", "libx264", "-preset", constants.VIDEO_PRESET,
            "-crf", str(constants.VIDEO_CRF), "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-r", str(fps),
            "-t", f"{spec.duration_s:.6f}", "-movflags", "+faststart",
            "-f", "mp4", str(temporary),
        ]
        try:
            self._ffmpeg.run_with_progress(
                args, spec.duration_s, on_progress, cancel
            )
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise MediaError("Segment normalization produced no output file.")
            info = self._ffmpeg.probe(temporary)
            if not info.has_video or info.is_image:
                raise MediaError("Normalized segment does not contain a video stream.")
            if info.has_audio:
                raise MediaError("Normalized segment unexpectedly contains an audio stream.")
            if (info.width, info.height) != (width, height):
                raise MediaError(
                    f"Normalized segment dimensions are {info.width}x{info.height}; "
                    f"expected {width}x{height}."
                )
            if info.duration_s is None:
                raise MediaError("Normalized segment has no measurable duration.")
            tolerance = max(0.1, 2.0 / fps)
            if abs(info.duration_s - spec.duration_s) > tolerance:
                raise MediaError(
                    f"Normalized segment duration is {info.duration_s:.3f}s; "
                    f"expected about {spec.duration_s:.3f}s."
                )
            os.replace(temporary, destination)
            return NormalizedSegment(
                path=destination,
                duration_s=info.duration_s,
                width=width,
                height=height,
                fps=fps,
            )
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
