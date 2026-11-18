"""CPU-first raster renderer for still-image scene compositions.

This module produces real transparent PNG frames from already-bound local
raster assets. It does not generate artwork, encode video, or mutate projects.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional

from PIL import Image, ImageOps

from app.models.project import Project
from app.universal.composition import SceneComposition
from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.models import UniversalState
from app.universal.visual_assets import VisualAsset


RASTER_RENDERER_VERSION = "1.0.0"
_SUPPORTED_FORMATS = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/gif": "GIF",
    "image/bmp": "BMP",
}


class RasterRenderError(RuntimeError):
    """Raised when a composition cannot be rendered safely."""


class RasterRenderCancelledError(RasterRenderError):
    """Raised when a render is cancelled before atomic output commit."""


@dataclass(frozen=True)
class RasterRenderLimits:
    """Hard limits applied before image decoding and canvas allocation."""

    max_width: int = 4096
    max_height: int = 4096
    max_canvas_pixels: int = 8_388_608
    max_asset_file_bytes: int = 100 * 1024 * 1024
    max_asset_pixels: int = 40_000_000

    def __post_init__(self) -> None:
        for name in ("max_width", "max_height", "max_canvas_pixels",
                     "max_asset_file_bytes", "max_asset_pixels"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class RasterRenderResult:
    destination: Path
    width: int
    height: int
    rendered_element_ids: tuple[str, ...]
    output_sha256: str
    renderer_version: str = RASTER_RENDERER_VERSION


def _cancelled(cancel) -> bool:
    if cancel is None:
        return False
    if isinstance(cancel, bool):
        return cancel
    is_set = getattr(cancel, "is_set", None)
    if callable(is_set):
        return bool(is_set())
    if callable(cancel):
        return bool(cancel())
    raise RasterRenderError("cancel must be a boolean, callable, or event-like object")


def _check_cancel(cancel) -> None:
    if _cancelled(cancel):
        raise RasterRenderCancelledError("Raster composition render was cancelled")


def _resolve_regular_file(path_value: os.PathLike[str] | str) -> Path:
    try:
        candidate = Path(path_value).expanduser()
        if candidate.is_symlink():
            raise RasterRenderError("Symbolic-link image paths are not accepted")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_file():
            raise RasterRenderError("Every visible composition asset must be a regular file")
        return resolved
    except (OSError, TypeError, ValueError) as exc:
        if isinstance(exc, RasterRenderError):
            raise
        raise RasterRenderError(f"Cannot resolve composition asset: {exc}") from exc


def resolve_scene_composition_assets(
    project: Project,
    composition: SceneComposition,
    library: VisualAssetLibrary,
) -> dict[str, Path]:
    """Resolve visible composition assets through scene bindings and the local catalog.

    AssetRef paths are not trusted as arbitrary filesystem paths. The catalog
    identity, scene binding, managed-library path and content hash must agree.
    """
    if not isinstance(project, Project) or not isinstance(composition, SceneComposition):
        raise RasterRenderError("project and composition must be valid domain objects")
    if not isinstance(library, VisualAssetLibrary):
        raise RasterRenderError("library must be a VisualAssetLibrary")
    if project.get_scene(composition.scene_id) is None:
        raise RasterRenderError("Composition scene does not exist in this project")

    state = UniversalState.from_project_settings(project.settings)
    if state.read_only:
        raise RasterRenderError("Universal project state is read-only")
    plan = state.scene_plans.get(composition.scene_id)
    bound_refs = {item.asset_id: item for item in plan.asset_refs} if plan else {}
    catalog = library.load_catalog()
    catalog_assets = {item.asset_id: item for item in catalog.assets}

    resolved: dict[str, Path] = {}
    for asset_id in sorted({item.asset_id for item in composition.elements if item.visible}):
        ref = bound_refs.get(asset_id)
        if ref is None:
            raise RasterRenderError(f"Asset '{asset_id}' is not bound to the composition scene")
        asset = catalog_assets.get(asset_id)
        if asset is None:
            raise RasterRenderError(f"Asset '{asset_id}' is missing from the local visual catalog")
        if ref.kind != "image" or asset.kind != "image":
            raise RasterRenderError(f"Asset '{asset_id}' is not a supported image asset")
        if ref.path != asset.location:
            raise RasterRenderError(f"Asset '{asset_id}' catalog location does not match its scene binding")
        if ref.identity is not None and ref.identity != asset.content_sha256:
            raise RasterRenderError(f"Asset '{asset_id}' content identity does not match its scene binding")
        try:
            path = library.resolve_asset_path(asset)
            if not library.verify_asset(asset):
                raise RasterRenderError(f"Asset '{asset_id}' failed its content hash verification")
        except AssetImportError as exc:
            raise RasterRenderError(f"Cannot resolve asset '{asset_id}': {exc}") from exc
        resolved[asset_id] = path
    return resolved


class RasterCompositionRenderer:
    """Deterministic CPU renderer for one still-image composition frame."""

    def __init__(self, limits: Optional[RasterRenderLimits] = None) -> None:
        self.limits = limits or RasterRenderLimits()
        if not isinstance(self.limits, RasterRenderLimits):
            raise ValueError("limits must be RasterRenderLimits")

    def _load_image(self, path: Path) -> Image.Image:
        try:
            size = path.stat().st_size
            if size <= 0 or size > self.limits.max_asset_file_bytes:
                raise RasterRenderError("Image file is empty or exceeds the configured byte limit")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as probe:
                    width, height = probe.size
                    if width <= 0 or height <= 0 or width * height > self.limits.max_asset_pixels:
                        raise RasterRenderError("Image dimensions exceed the configured pixel limit")
                    if probe.format not in _SUPPORTED_FORMATS.values():
                        raise RasterRenderError("Only PNG, JPEG, GIF and BMP assets can be rendered")
                    probe.verify()
                with Image.open(path) as source:
                    if source.format not in _SUPPORTED_FORMATS.values():
                        raise RasterRenderError("Unsupported raster image format")
                    source.seek(0)  # GIF input is deliberately rendered as its first frame.
                    image = ImageOps.exif_transpose(source).convert("RGBA")
                    image.load()
                    return image
        except RasterRenderError:
            raise
        except (OSError, ValueError, Image.DecompressionBombError,
                Image.DecompressionBombWarning) as exc:
            raise RasterRenderError(f"Cannot safely decode image '{path.name}': {exc}") from exc

    @staticmethod
    def _fit(image: Image.Image, width: int, height: int, mode: str) -> Image.Image:
        if mode == "stretch":
            return image.resize((width, height), Image.Resampling.LANCZOS)
        if mode == "contain":
            fitted = ImageOps.contain(image, (width, height), method=Image.Resampling.LANCZOS)
            result = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            result.alpha_composite(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
            return result
        if mode == "cover":
            return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        raise RasterRenderError(f"Unsupported fit mode: {mode}")

    def render(
        self,
        composition: SceneComposition,
        *,
        asset_paths: Mapping[str, os.PathLike[str] | str],
        destination: os.PathLike[str] | str,
        overwrite: bool = False,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel=None,
    ) -> RasterRenderResult:
        """Render one composition to a PNG using an atomic destination write."""
        if not isinstance(composition, SceneComposition):
            raise RasterRenderError("composition must be a SceneComposition")
        if not isinstance(asset_paths, Mapping):
            raise RasterRenderError("asset_paths must be a mapping")
        if not isinstance(overwrite, bool):
            raise RasterRenderError("overwrite must be a boolean")
        canvas_spec = composition.canvas
        width, height = canvas_spec.width, canvas_spec.height
        if width > self.limits.max_width or height > self.limits.max_height:
            raise RasterRenderError("Composition canvas exceeds configured width or height limits")
        if width * height > self.limits.max_canvas_pixels:
            raise RasterRenderError("Composition canvas exceeds configured pixel limit")

        visible_ids = {item.asset_id for item in composition.elements if item.visible}
        if set(asset_paths) != visible_ids:
            raise RasterRenderError("asset_paths must contain exactly the visible composition asset IDs")
        paths = {asset_id: _resolve_regular_file(value) for asset_id, value in asset_paths.items()}

        target = Path(destination).expanduser()
        if target.suffix.lower() != ".png":
            raise RasterRenderError("Raster composition output destination must use the .png extension")
        if target.is_symlink():
            raise RasterRenderError("Output destination must not be a symbolic link")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise RasterRenderError("Output already exists; pass overwrite=True to replace it")
        if target.exists() and not target.is_file():
            raise RasterRenderError("Output destination must be a regular file")

        elements = sorted(
            (item for item in composition.elements if item.visible),
            key=lambda item: (item.layer_order, item.element_id),
        )
        rendered_ids: list[str] = []
        temp_path: Optional[Path] = None
        try:
            _check_cancel(cancel)
            frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            if on_progress:
                on_progress(0.0)
            for index, element in enumerate(elements):
                _check_cancel(cancel)
                source = self._load_image(paths[element.asset_id])
                transform = element.transform
                left = round(transform.x * width)
                top = round(transform.y * height)
                box_width = min(max(1, round(transform.width * width)), width - left)
                box_height = min(max(1, round(transform.height * height)), height - top)
                fitted = self._fit(source, box_width, box_height, element.fit_mode)
                source.close()
                if transform.opacity < 1.0:
                    alpha = fitted.getchannel("A").point(lambda value: round(value * transform.opacity))
                    fitted.putalpha(alpha)

                layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                layer.alpha_composite(fitted, (left, top))
                fitted.close()

                if transform.rotation_degrees:
                    anchor = (
                        left + transform.anchor_x * box_width,
                        top + transform.anchor_y * box_height,
                    )
                    rotated = layer.rotate(
                        -transform.rotation_degrees,
                        resample=Image.Resampling.BICUBIC,
                        center=anchor,
                        expand=False,
                    )
                    layer.close()
                    layer = rotated
                frame = Image.alpha_composite(frame, layer)
                layer.close()
                rendered_ids.append(element.element_id)
                if on_progress:
                    on_progress((index + 1) / max(1, len(elements)))

            _check_cancel(cancel)
            fd, name = tempfile.mkstemp(prefix=".voxora-render-", suffix=".png", dir=str(target.parent))
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as stream:
                frame.save(stream, format="PNG", optimize=False)
                stream.flush()
                os.fsync(stream.fileno())
            frame.close()
            _check_cancel(cancel)
            if overwrite:
                os.replace(temp_path, target)
                temp_path = None
            else:
                try:
                    os.link(temp_path, target)
                except FileExistsError:
                    raise RasterRenderError("Output appeared during rendering; refusing to overwrite it") from None
                temp_path.unlink()
                temp_path = None
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return RasterRenderResult(target, width, height, tuple(rendered_ids), digest.hexdigest())
        except RasterRenderError:
            raise
        except Exception as exc:
            raise RasterRenderError(f"Raster composition render failed: {exc}") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass


def render_bound_scene_composition(
    project: Project,
    composition: SceneComposition,
    library: VisualAssetLibrary,
    destination: os.PathLike[str] | str,
    *,
    renderer: Optional[RasterCompositionRenderer] = None,
    overwrite: bool = False,
    on_progress: Optional[Callable[[float], None]] = None,
    cancel=None,
) -> RasterRenderResult:
    """Resolve catalog-backed scene bindings, verify hashes, then render a PNG."""
    asset_paths = resolve_scene_composition_assets(project, composition, library)
    active_renderer = renderer or RasterCompositionRenderer()
    return active_renderer.render(
        composition,
        asset_paths=asset_paths,
        destination=destination,
        overwrite=overwrite,
        on_progress=on_progress,
        cancel=cancel,
    )
