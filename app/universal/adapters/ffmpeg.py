"""Universal Core adapter for Voxora's existing FFmpeg segment renderer.

This adapter deliberately delegates to the existing SegmentSpec and
build_segment_args implementation. It does not replace the renderer or own
joining, audio mixing, muxing, caching, or timeline calculation.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Optional

from app.core import constants
from app.universal.engines import EngineCapabilities, EngineDescriptor
from app.video.render import SegmentSpec, build_segment_args
from app.workers.cancel import CancelToken


class FFmpegSegmentAdapter:
    """Execute one existing FFmpeg scene-segment render through a stable adapter."""

    engine_id = "ffmpeg"

    def __init__(self, ffmpeg) -> None:
        self._ffmpeg = ffmpeg
        self.descriptor = EngineDescriptor(
            engine_id=self.engine_id,
            display_name="FFmpeg Segment Renderer",
            version=f"pipeline-{constants.VIDEO_PIPELINE_VERSION}",
            capabilities=EngineCapabilities(
                scene_kinds=("blank", "image", "video"),
                asset_kinds=("image", "video"),
                output_formats=("mp4",),
                requires_gpu=False,
                supports_draft_render=True,
                max_concurrent_jobs=1,
            ),
        )

    @staticmethod
    def validate_spec(spec: SegmentSpec) -> None:
        """Reject unsupported or malformed requests rather than guessing a mode."""
        if not isinstance(spec, SegmentSpec):
            raise TypeError("spec must be a SegmentSpec")
        if spec.kind not in ("blank", "image", "video"):
            raise ValueError(f"unsupported FFmpeg segment kind: {spec.kind!r}")
        if isinstance(spec.length_s, bool) or not isinstance(spec.length_s, (int, float)):
            raise ValueError("segment length must be a positive finite number")
        try:
            finite_length = math.isfinite(float(spec.length_s))
        except (OverflowError, ValueError):
            finite_length = False
        if not finite_length or spec.length_s <= 0:
            raise ValueError("segment length must be a positive finite number")
        for name in ("width", "height", "fps"):
            value = getattr(spec, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"segment {name} must be a positive integer")
        if spec.kind in ("image", "video") and (
            not isinstance(spec.media, str) or not spec.media.strip()
        ):
            raise ValueError(f"{spec.kind} segments require a media path")
        if spec.kind == "blank" and spec.media is not None:
            raise ValueError("blank segments must not specify a media path")
        if spec.motion not in ("none", "zoom_in", "zoom_out", "pan_left", "pan_right"):
            raise ValueError(f"unsupported segment motion: {spec.motion!r}")
        if spec.fit not in ("fit", "fill"):
            raise ValueError(f"unsupported segment fit mode: {spec.fit!r}")

    def render_request(
        self,
        request,
        *,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[CancelToken] = None,
    ) -> Path:
        """Render an immutable Universal request through the existing segment renderer.

        This production bridge intentionally returns the already-normalized
        silent MP4 segment. It avoids a second encode through SegmentNormalizer
        while retaining the legacy renderer's exact output and timing behavior.
        """
        from app.universal.requests import EngineRenderRequest

        if not isinstance(request, EngineRenderRequest):
            raise TypeError("request must be an EngineRenderRequest")
        if request.output_format != "mp4":
            raise ValueError("FFmpeg production adapter only supports mp4 output")
        allowed_params = {"motion", "fit", "length_ticks", "frame_count"}
        unknown_params = set(request.engine_params) - allowed_params
        if unknown_params:
            raise ValueError(
                "unsupported FFmpeg request parameters: " + ", ".join(sorted(unknown_params))
            )

        if request.scene_kind == "blank":
            if request.asset_refs:
                raise ValueError("blank scene requests must not contain asset references")
            media = None
        elif request.scene_kind in ("image", "video"):
            if len(request.asset_refs) != 1:
                raise ValueError(
                    f"{request.scene_kind} scene requests require exactly one asset reference"
                )
            asset = request.asset_refs[0]
            if asset.kind != request.scene_kind or not asset.path:
                raise ValueError(
                    f"{request.scene_kind} scene request requires one matching asset path"
                )
            media = asset.path
        else:
            raise ValueError(f"unsupported FFmpeg scene kind: {request.scene_kind!r}")

        params = request.engine_params
        spec = SegmentSpec(
            kind=request.scene_kind,
            media=media,
            length_s=request.output_spec.duration_s,
            width=request.output_spec.width,
            height=request.output_spec.height,
            fps=request.output_spec.fps,
            motion=params.get("motion", "none"),
            fit=params.get("fit", "fill"),
            length_ticks=params.get("length_ticks"),
            frame_count=params.get("frame_count"),
        )
        return self.render_segment(
            spec,
            request.destination,
            on_progress=on_progress,
            cancel=cancel,
        )

    def render_segment(
        self,
        spec: SegmentSpec,
        destination: Path,
        *,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[CancelToken] = None,
    ) -> Path:
        """Render a silent MP4 segment to destination using the legacy FFmpeg path."""
        self.validate_spec(spec)
        destination = Path(destination)
        args = build_segment_args(self._ffmpeg.require(), spec, destination)
        self._ffmpeg.run_with_progress(args, spec.length_s, on_progress, cancel)
        return destination
