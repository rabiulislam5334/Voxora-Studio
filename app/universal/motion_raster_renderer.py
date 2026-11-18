"""Motion-aware CPU raster rendering for animated composition frames.

This module evaluates the existing deterministic motion contracts and applies
those values to real raster pixels. It intentionally stops at PNG frame
sequences; video encoding and project/UI integration remain separate stages.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Mapping, Optional

from PIL import Image

from app.universal.composition import SceneComposition, VisualTransform
from app.universal.motion import (
    EvaluatedMotionFrame,
    MotionValidationError,
    SceneMotion,
    evaluate_scene_motion,
)
from app.universal.raster_renderer import (
    RasterCompositionRenderer,
    RasterRenderCancelledError,
    RasterRenderError,
)


class MotionRasterRenderError(RuntimeError):
    """Raised when an animated raster frame cannot be rendered safely."""


class MotionRasterRenderCancelledError(MotionRasterRenderError):
    """Raised when an animated frame or sequence is cancelled."""


@dataclass(frozen=True)
class MotionRasterRenderResult:
    destination: Path
    frame: int
    width: int
    height: int
    rendered_element_ids: tuple[str, ...]
    output_sha256: str


@dataclass(frozen=True)
class MotionRasterSequenceResult:
    destination: Path
    frame_paths: tuple[Path, ...]
    frame_count: int
    width: int
    height: int


def _check_cancel(cancel) -> None:
    if cancel is None:
        return
    if isinstance(cancel, bool):
        cancelled = cancel
    else:
        is_set = getattr(cancel, "is_set", None)
        if callable(is_set):
            cancelled = bool(is_set())
        elif callable(cancel):
            cancelled = bool(cancel())
        else:
            raise MotionRasterRenderError(
                "cancel must be a boolean, callable, or event-like object"
            )
    if cancelled:
        raise MotionRasterRenderCancelledError("Motion raster rendering was cancelled")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _evaluated_composition(
    composition: SceneComposition,
    evaluated: EvaluatedMotionFrame,
) -> SceneComposition:
    """Build an ephemeral composition with the evaluated element properties."""
    elements = []
    for element in composition.elements:
        transform = element.transform
        values = {
            name: evaluated.value_for("element", element.element_id, name)
            for name in (
                "x", "y", "width", "height", "anchor_x", "anchor_y",
                "rotation_degrees", "opacity",
            )
        }
        changes = {name: value for name, value in values.items() if value is not None}
        if changes:
            transform = replace(transform, **changes)
            element = replace(element, transform=transform)
        elements.append(element)
    return replace(composition, elements=tuple(elements))


def _apply_camera(
    image: Image.Image,
    evaluated: EvaluatedMotionFrame,
) -> Image.Image:
    """Apply camera rotation, zoom and normalized canvas pan to a rendered frame.

    pan_x=1 moves the image right by one canvas width; pan_y=1 moves it down
    by one canvas height. Zoom is centered on the canvas midpoint.
    """
    width, height = image.size
    rotation = evaluated.value_for("camera", "camera", "rotation_degrees") or 0.0
    zoom = evaluated.value_for("camera", "camera", "zoom")
    pan_x = evaluated.value_for("camera", "camera", "pan_x") or 0.0
    pan_y = evaluated.value_for("camera", "camera", "pan_y") or 0.0
    zoom = 1.0 if zoom is None else zoom

    result = image
    if rotation:
        result = result.rotate(
            -rotation,
            resample=Image.Resampling.BICUBIC,
            center=(width / 2.0, height / 2.0),
            expand=False,
        )
        image.close()

    if zoom != 1.0 or pan_x != 0.0 or pan_y != 0.0:
        center_x, center_y = width / 2.0, height / 2.0
        translate_x, translate_y = pan_x * width, pan_y * height
        inverse = (
            1.0 / zoom, 0.0, center_x - (center_x + translate_x) / zoom,
            0.0, 1.0 / zoom, center_y - (center_y + translate_y) / zoom,
        )
        transformed = result.transform(
            (width, height),
            Image.Transform.AFFINE,
            inverse,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )
        result.close()
        result = transformed
    return result


def _atomic_save_png(image: Image.Image, destination: Path, *, overwrite: bool) -> None:
    target = destination.expanduser()
    if target.suffix.lower() != ".png":
        raise MotionRasterRenderError("frame destination must use the .png extension")
    if target.is_symlink():
        raise MotionRasterRenderError("frame destination must not be a symbolic link")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not overwrite:
        raise MotionRasterRenderError(
            "frame destination already exists; explicit overwrite is required"
        )
    if target.exists() and not target.is_file():
        raise MotionRasterRenderError("frame destination must be a regular file")

    temp_path: Optional[Path] = None
    try:
        fd, name = tempfile.mkstemp(
            prefix=".voxora-motion-frame-", suffix=".png", dir=str(target.parent)
        )
        temp_path = Path(name)
        with os.fdopen(fd, "wb") as stream:
            image.save(stream, format="PNG", optimize=False)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temp_path, target)
            temp_path = None
        else:
            try:
                os.link(temp_path, target)
            except FileExistsError:
                raise MotionRasterRenderError(
                    "frame destination appeared during rendering; refusing to overwrite it"
                ) from None
            temp_path.unlink()
            temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class MotionRasterRenderer:
    """Render one motion-evaluated PNG frame or an atomic PNG frame sequence."""

    def __init__(
        self,
        renderer: Optional[RasterCompositionRenderer] = None,
        *,
        max_sequence_frames: int = 900,
    ) -> None:
        self._renderer = renderer or RasterCompositionRenderer()
        if not isinstance(self._renderer, RasterCompositionRenderer):
            raise TypeError("renderer must be a RasterCompositionRenderer")
        if (
            isinstance(max_sequence_frames, bool)
            or not isinstance(max_sequence_frames, int)
            or max_sequence_frames <= 0
        ):
            raise ValueError("max_sequence_frames must be a positive integer")
        self.max_sequence_frames = max_sequence_frames

    def render_frame(
        self,
        composition: SceneComposition,
        motion: SceneMotion,
        frame: int,
        *,
        asset_paths: Mapping[str, os.PathLike[str] | str],
        destination: os.PathLike[str] | str,
        overwrite: bool = False,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel=None,
    ) -> MotionRasterRenderResult:
        """Render a single evaluated motion frame to an atomic PNG."""
        if not isinstance(composition, SceneComposition):
            raise MotionRasterRenderError("composition must be a SceneComposition")
        if not isinstance(motion, SceneMotion):
            raise MotionRasterRenderError("motion must be a SceneMotion")
        if composition.scene_id != motion.scene_id:
            raise MotionRasterRenderError("motion and composition scene IDs do not match")
        if not isinstance(asset_paths, Mapping):
            raise MotionRasterRenderError("asset_paths must be a mapping")
        if not isinstance(overwrite, bool):
            raise MotionRasterRenderError("overwrite must be a boolean")
        _check_cancel(cancel)

        try:
            evaluated = evaluate_scene_motion(motion, frame, composition=composition)
            animated = _evaluated_composition(composition, evaluated)
        except (MotionValidationError, TypeError, ValueError) as exc:
            raise MotionRasterRenderError(f"Invalid scene motion: {exc}") from exc

        target = Path(destination).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        intermediate: Optional[Path] = None
        final_image: Optional[Image.Image] = None
        try:
            with tempfile.TemporaryDirectory(
                prefix=".voxora-motion-source-", dir=str(target.parent)
            ) as temporary:
                intermediate = Path(temporary) / "composition.png"
                rendered = self._renderer.render(
                    animated,
                    asset_paths=asset_paths,
                    destination=intermediate,
                    on_progress=on_progress,
                    cancel=cancel,
                )
                _check_cancel(cancel)
                with Image.open(rendered.destination) as source:
                    final_image = _apply_camera(source.convert("RGBA"), evaluated)
                _check_cancel(cancel)
                _atomic_save_png(final_image, target, overwrite=overwrite)
            return MotionRasterRenderResult(
                destination=target,
                frame=frame,
                width=composition.canvas.width,
                height=composition.canvas.height,
                rendered_element_ids=rendered.rendered_element_ids,
                output_sha256=_sha256(target),
            )
        except RasterRenderCancelledError as exc:
            raise MotionRasterRenderCancelledError(str(exc)) from exc
        except (RasterRenderError, OSError, ValueError) as exc:
            if isinstance(exc, MotionRasterRenderError):
                raise
            raise MotionRasterRenderError(f"Animated frame render failed: {exc}") from exc
        finally:
            if final_image is not None:
                final_image.close()

    def render_sequence(
        self,
        composition: SceneComposition,
        motion: SceneMotion,
        *,
        asset_paths: Mapping[str, os.PathLike[str] | str],
        destination_dir: os.PathLike[str] | str,
        on_progress: Optional[Callable[[float, str], None]] = None,
        cancel=None,
    ) -> MotionRasterSequenceResult:
        """Render every motion frame into a staged directory, then publish atomically.

        Existing destination directories are never overwritten. If a frame
        fails or cancellation is requested, the staged directory is removed.
        """
        if not isinstance(composition, SceneComposition):
            raise MotionRasterRenderError("composition must be a SceneComposition")
        if not isinstance(motion, SceneMotion):
            raise MotionRasterRenderError("motion must be a SceneMotion")
        if composition.scene_id != motion.scene_id:
            raise MotionRasterRenderError("motion and composition scene IDs do not match")
        if motion.duration_frames > self.max_sequence_frames:
            raise MotionRasterRenderError(
                f"sequence exceeds the configured {self.max_sequence_frames}-frame limit"
            )
        if on_progress is not None and not callable(on_progress):
            raise MotionRasterRenderError("on_progress must be callable")

        target = Path(destination_dir).expanduser()
        if target.is_symlink():
            raise MotionRasterRenderError("sequence destination must not be a symbolic link")
        if target.exists():
            raise MotionRasterRenderError(
                "sequence destination already exists; refusing to overwrite it"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(
            prefix=".voxora-motion-sequence-", dir=str(target.parent)
        ))
        frame_names: list[str] = []
        try:
            for frame in range(motion.duration_frames):
                _check_cancel(cancel)
                name = f"frame_{frame:06d}.png"
                frame_path = staging / name

                def report(fraction: float, current=frame) -> None:
                    if on_progress:
                        overall = (current + max(0.0, min(1.0, fraction))) / motion.duration_frames
                        on_progress(overall, f"Rendering frame {current + 1}/{motion.duration_frames}")

                self.render_frame(
                    composition, motion, frame,
                    asset_paths=asset_paths,
                    destination=frame_path,
                    on_progress=lambda fraction: report(fraction),
                    cancel=cancel,
                )
                frame_names.append(name)

            _check_cancel(cancel)
            if target.exists() or target.is_symlink():
                raise MotionRasterRenderError(
                    "sequence destination appeared during rendering; refusing to overwrite it"
                )
            os.rename(staging, target)
            frame_paths = tuple(target / name for name in frame_names)
            if on_progress:
                on_progress(1.0, "Motion frame sequence complete")
            return MotionRasterSequenceResult(
                destination=target,
                frame_paths=frame_paths,
                frame_count=len(frame_paths),
                width=composition.canvas.width,
                height=composition.canvas.height,
            )
        except RasterRenderCancelledError as exc:
            raise MotionRasterRenderCancelledError(str(exc)) from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
