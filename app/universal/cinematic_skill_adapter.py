"""Adapter for the MIT Cinematic Skill Skia renderer.

The upstream renderer produces RGB frames. Voxora owns job lifecycle, temporary
files, cancellation, frame validation, FFmpeg encoding and the later narration
mux stage. This adapter deliberately emits a silent MP4; it never regenerates,
trims or replaces user-supplied narration.
"""
from __future__ import annotations

import hashlib
import math
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

from PIL import Image

from app.universal.frame_sequence import (
    FFmpegFrameSequenceEncoder,
    FrameSequence,
    FrameSequenceCancelledError,
    FrameSequenceError,
)


class CinematicSkillUnavailableError(RuntimeError):
    """Raised when optional Skia/NumPy runtime dependencies are unavailable."""


class CinematicSkillRenderError(RuntimeError):
    """Raised when a Cinematic Skill frame sequence cannot be rendered safely."""


class CinematicSkillRenderCancelledError(CinematicSkillRenderError):
    """Raised when a Cinematic Skill render is cancelled."""


@dataclass(frozen=True)
class CinematicSkillRenderResult:
    """Verified silent MP4 artifact emitted by the upstream cinematic renderer."""

    destination: Path
    frame_count: int
    fps: int
    width: int
    height: int
    duration_seconds: float
    output_sha256: str
    codec: str = "h264"
    audio_included: bool = False


def _is_cancelled(cancel) -> bool:
    if cancel is None:
        return False
    if isinstance(cancel, bool):
        return cancel
    value = getattr(cancel, "cancelled", None)
    if value is not None:
        return bool(value)
    is_set = getattr(cancel, "is_set", None)
    if callable(is_set):
        return bool(is_set())
    if callable(cancel):
        return bool(cancel())
    raise CinematicSkillRenderError(
        "cancel must be a boolean, callable, event-like object, or CancelToken"
    )


def _renderer_factory():
    try:
        from app.universal.cinematic_skill.engine import Renderer
    except (ImportError, OSError) as exc:
        raise CinematicSkillUnavailableError(
            "Cinematic Skill requires the optional NumPy, Pillow and skia-python "
            "runtime. Install requirements-cinematic-skill.txt; no paid service "
            "or API key is used."
        ) from exc
    return Renderer


def _prepare_project_context(project_dir: Path):
    """Create the board textures required by the upstream Film look definitions."""
    prep = project_dir / "assets" / "prep"
    prep.mkdir(parents=True, exist_ok=True)
    try:
        from app.universal.cinematic_skill.prep_assets import textures
        textures(prep)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise CinematicSkillUnavailableError(
            f"could not prepare local Cinematic Skill board textures: {exc}"
        ) from exc
    return SimpleNamespace(dir=project_dir, prep=prep)


class CinematicSkillRenderCoordinator:
    """Render one upstream Film sequentially, then encode through Voxora FFmpeg.

    The caller supplies a Film built by a trusted Voxora Director/scene factory.
    Rendering is single-worker and bounded to 1080p by default for low-memory PCs.
    The result is silent by design so Voxora's existing audio-mux workflow can
    attach the original narration without changing its timing or content.
    """

    def __init__(
        self,
        *,
        encoder=None,
        renderer_factory: Optional[Callable] = None,
        max_width: int = 1920,
        max_height: int = 1080,
        max_frames: int = 180_000,
    ) -> None:
        self._encoder = encoder or FFmpegFrameSequenceEncoder()
        if not callable(getattr(self._encoder, "encode", None)):
            raise TypeError("encoder must provide an encode(sequence, destination) method")
        self._uses_upstream_renderer = renderer_factory is None
        self._renderer_factory = renderer_factory or _renderer_factory
        for name, value in (
            ("max_width", max_width),
            ("max_height", max_height),
            ("max_frames", max_frames),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self.max_width = max_width
        self.max_height = max_height
        self.max_frames = max_frames

    def render(
        self,
        film,
        destination: os.PathLike[str] | str,
        *,
        width: int = 1280,
        height: int = 720,
        doc=None,
        cancel=None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> CinematicSkillRenderResult:
        """Render a Film to a silent MP4 using Voxora's existing frame encoder."""
        if film is None:
            raise CinematicSkillRenderError("film is required")
        if isinstance(width, bool) or not isinstance(width, int) or not 1 <= width <= self.max_width:
            raise CinematicSkillRenderError(f"width must be between 1 and {self.max_width}")
        if isinstance(height, bool) or not isinstance(height, int) or not 1 <= height <= self.max_height:
            raise CinematicSkillRenderError(f"height must be between 1 and {self.max_height}")
        if width * height > self.max_width * self.max_height:
            raise CinematicSkillRenderError("requested canvas exceeds the configured pixel budget")
        if on_progress is not None and not callable(on_progress):
            raise CinematicSkillRenderError("on_progress must be callable")

        try:
            duration = float(film.duration)
            fps = film.fps
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            raise CinematicSkillRenderError("film must expose numeric duration and integer fps") from exc
        if not math.isfinite(duration) or duration <= 0:
            raise CinematicSkillRenderError("film.duration must be a finite positive number")
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 60:
            raise CinematicSkillRenderError("film.fps must be an integer between 1 and 60")

        frame_count = max(1, math.ceil(duration * fps - 1e-9))
        if frame_count > self.max_frames:
            raise CinematicSkillRenderError(
                f"film exceeds the configured {self.max_frames}-frame limit"
            )

        target = Path(destination).expanduser()
        if target.suffix.lower() != ".mp4":
            raise CinematicSkillRenderError("destination must use the .mp4 extension")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise CinematicSkillRenderError("destination must be a regular file, not a symlink")
        if target.exists():
            raise CinematicSkillRenderError(
                "destination already exists; refusing to overwrite an existing artifact"
            )
        target.parent.mkdir(parents=True, exist_ok=True)

        staging = Path(tempfile.mkdtemp(prefix=".voxora-cinematic-", dir=str(target.parent)))
        frames_dir = staging / "frames"
        frames_dir.mkdir()
        silent_video = staging / "silent.mp4"
        frame_paths: list[Path] = []

        try:
            render_doc = doc
            if self._uses_upstream_renderer and render_doc is None:
                render_doc = _prepare_project_context(staging / "project")
            try:
                renderer_type = self._renderer_factory()
                renderer = renderer_type(film, width=width, height=height, doc=render_doc)
            except CinematicSkillUnavailableError:
                raise
            except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
                raise CinematicSkillRenderError(
                    f"could not initialise Cinematic Skill renderer: {exc}"
                ) from exc

            for index in range(frame_count):
                if _is_cancelled(cancel):
                    raise CinematicSkillRenderCancelledError(
                        "Cinematic Skill rendering was cancelled"
                    )
                try:
                    frame = renderer.frame(index)
                    if isinstance(frame, Image.Image):
                        image = frame.convert("RGB")
                    else:
                        image = Image.fromarray(frame).convert("RGB")
                    try:
                        if image.size != (width, height):
                            raise CinematicSkillRenderError(
                                f"renderer returned {image.size}, expected {(width, height)}"
                            )
                        frame_path = frames_dir / f"frame_{index:06d}.png"
                        image.save(frame_path, format="PNG", optimize=False)
                    finally:
                        image.close()
                except CinematicSkillRenderError:
                    raise
                except SystemExit as exc:
                    raise CinematicSkillRenderError(
                        f"Cinematic Skill scene is not renderable: {exc}"
                    ) from exc
                except Exception as exc:
                    raise CinematicSkillRenderError(
                        f"Cinematic Skill failed at frame {index}: {exc}"
                    ) from exc

                frame_paths.append(frame_path)
                if on_progress:
                    on_progress(
                        0.75 * ((index + 1) / frame_count),
                        f"Rendering cinematic frame {index + 1}/{frame_count}",
                    )

            if _is_cancelled(cancel):
                raise CinematicSkillRenderCancelledError(
                    "Cinematic Skill rendering was cancelled"
                )

            sequence = FrameSequence(tuple(frame_paths), fps)

            def encode_progress(fraction: float) -> None:
                if on_progress:
                    bounded = max(0.0, min(1.0, float(fraction)))
                    on_progress(0.75 + bounded * 0.25, "Encoding and verifying silent MP4")

            try:
                encoded = self._encoder.encode(
                    sequence,
                    silent_video,
                    on_progress=encode_progress if on_progress else None,
                    cancel=cancel,
                )
            except FrameSequenceCancelledError as exc:
                raise CinematicSkillRenderCancelledError(str(exc)) from exc
            except FrameSequenceError as exc:
                raise CinematicSkillRenderError(
                    f"FFmpeg frame encoding failed: {exc}"
                ) from exc

            if _is_cancelled(cancel):
                raise CinematicSkillRenderCancelledError(
                    "Cinematic Skill render was cancelled"
                )
            if not silent_video.is_file() or silent_video.stat().st_size <= 0:
                raise CinematicSkillRenderError(
                    "FFmpeg encoder did not produce a non-empty MP4"
                )

            digest = hashlib.sha256()
            with silent_video.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)

            # Hard-link publication is atomic and cannot replace a file created
            # by another process between the initial existence check and commit.
            try:
                os.link(silent_video, target)
            except FileExistsError:
                raise CinematicSkillRenderError(
                    "destination appeared during rendering; refusing to overwrite it"
                ) from None
            silent_video.unlink()

            if on_progress:
                on_progress(1.0, "Cinematic Skill silent MP4 complete")

            return CinematicSkillRenderResult(
                destination=target,
                frame_count=frame_count,
                fps=fps,
                width=width,
                height=height,
                duration_seconds=frame_count / fps,
                output_sha256=digest.hexdigest(),
                codec=getattr(encoded, "codec", "h264"),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
