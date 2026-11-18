"""Explicit capability bridge for scene-composition renderers.

The current FFmpeg segment adapter renders one blank/image/video source per
scene and does not implement layered composition rendering. This bridge
therefore reports it as unsupported rather than silently flattening or
dropping composition elements. Future adapters must opt in with a declared
CompositionRenderCapabilities value and a render_composition() method.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Tuple

from app.models.project import Project
from app.universal.composition import SceneComposition
from app.universal.composition_workflow import (
    SceneCompositionPreview,
    preview_scene_composition,
)
from app.universal.engines import EngineDescriptor
from app.universal.models import UniversalState


class CompositionRenderBridgeError(RuntimeError):
    """Base error for explicit composition render capability resolution."""


class CompositionRenderUnsupportedError(CompositionRenderBridgeError):
    """Raised when the exact requested engine cannot render layered compositions."""


class CompositionRenderApprovalError(CompositionRenderBridgeError):
    """Raised when composition rendering has not been explicitly approved."""


@dataclass(frozen=True)
class CompositionRenderCapabilities:
    """Features a renderer explicitly promises for layered composition input."""

    output_formats: Tuple[str, ...] = ("mp4",)
    asset_kinds: Tuple[str, ...] = ("image",)
    supports_layers: bool = True
    supports_transforms: bool = True
    supports_opacity: bool = True
    supports_rotation: bool = True

    def __post_init__(self):
        for name in ("output_formats", "asset_kinds"):
            values = getattr(self, name)
            if isinstance(values, (str, bytes)):
                raise ValueError(f"{name} must be a sequence of strings")
            values = tuple(values)
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise ValueError(f"{name} must contain non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, values)
        for name in (
            "supports_layers", "supports_transforms", "supports_opacity", "supports_rotation"
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class CompositionRenderResolution:
    engine_id: str
    supported: bool
    output_formats: Tuple[str, ...] = ()
    reason: str = ""


class CompositionRendererAdapter(Protocol):
    descriptor: EngineDescriptor
    composition_capabilities: CompositionRenderCapabilities

    def render_composition(
        self,
        composition: SceneComposition,
        *,
        asset_paths: Mapping[str, Path],
        destination: Path,
        output_format: str,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel=None,
    ) -> Path: ...


class CompositionRenderBridge:
    """Resolve and invoke only explicitly registered composition renderers.

    This registry is intentionally independent from EngineRuntimeRegistry:
    a scene-segment adapter is not assumed to support layered composition.
    There is no fallback, implicit flattening, or engine auto-selection.
    """

    def __init__(self, adapters: Optional[Mapping[str, object]] = None):
        self._adapters = dict(adapters or {})
        if any(not isinstance(key, str) or not key.strip() for key in self._adapters):
            raise ValueError("adapter keys must be non-empty engine IDs")

    def inspect(self, engine_id: str) -> CompositionRenderResolution:
        if not isinstance(engine_id, str) or not engine_id.strip():
            raise ValueError("engine_id must be a non-empty string")
        adapter = self._adapters.get(engine_id)
        if adapter is None:
            return CompositionRenderResolution(
                engine_id, False, reason="No composition renderer is registered for this engine."
            )
        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(descriptor, EngineDescriptor):
            return CompositionRenderResolution(
                engine_id, False, reason="Adapter does not expose a valid EngineDescriptor."
            )
        if descriptor.engine_id != engine_id:
            return CompositionRenderResolution(
                engine_id, False, reason="Adapter descriptor ID does not match the selected engine."
            )
        if not descriptor.available:
            return CompositionRenderResolution(
                engine_id, False, reason=descriptor.unavailable_reason or "Engine is unavailable."
            )
        capabilities = getattr(adapter, "composition_capabilities", None)
        if not isinstance(capabilities, CompositionRenderCapabilities):
            return CompositionRenderResolution(
                engine_id, False,
                reason="Adapter has not declared layered composition capabilities."
            )
        if not callable(getattr(adapter, "render_composition", None)):
            return CompositionRenderResolution(
                engine_id, False, reason="Adapter does not implement render_composition()."
            )
        if not capabilities.supports_layers or not capabilities.supports_transforms:
            return CompositionRenderResolution(
                engine_id, False,
                reason="Adapter must support layered composition and element transforms."
            )
        return CompositionRenderResolution(
            engine_id, True, capabilities.output_formats,
            reason="Adapter explicitly declares layered composition support."
        )

    def render(
        self,
        engine_id: str,
        project: Project,
        composition: SceneComposition,
        preview: SceneCompositionPreview,
        *,
        asset_paths: Mapping[str, Path],
        destination: Path,
        output_format: str = "mp4",
        approved: bool = False,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel=None,
    ) -> Path:
        if approved is not True:
            raise CompositionRenderApprovalError(
                "explicit approval is required before rendering a composition"
            )
        resolution = self.inspect(engine_id)
        if not resolution.supported:
            raise CompositionRenderUnsupportedError(resolution.reason)
        if output_format not in resolution.output_formats:
            raise CompositionRenderUnsupportedError(
                f"Engine '{engine_id}' does not declare output format '{output_format}'."
            )
        if not isinstance(preview, SceneCompositionPreview) or not preview.is_valid:
            raise CompositionRenderBridgeError("A valid composition preview is required.")
        current = preview_scene_composition(project, composition)
        if current != preview:
            raise CompositionRenderBridgeError(
                "Composition preview is stale; rebuild and review it before rendering."
            )
        if not isinstance(asset_paths, Mapping):
            raise CompositionRenderBridgeError("asset_paths must be a mapping.")
        state = UniversalState.from_project_settings(project.settings)
        if state.read_only:
            raise CompositionRenderBridgeError("Universal project state is read-only.")
        plan = state.scene_plans.get(composition.scene_id)
        bound_assets = {item.asset_id: item for item in plan.asset_refs} if plan else {}
        required_ids = {item.asset_id for item in composition.elements if item.visible}
        for asset_id in required_ids:
            asset_ref = bound_assets.get(asset_id)
            if asset_ref is None:
                raise CompositionRenderBridgeError(
                    f"Composition asset '{asset_id}' is not bound to the target scene."
                )
            if asset_ref.kind not in getattr(self._adapters[engine_id], "composition_capabilities").asset_kinds:
                raise CompositionRenderUnsupportedError(
                    f"Engine '{engine_id}' does not declare asset kind '{asset_ref.kind}'."
                )
        capabilities = getattr(self._adapters[engine_id], "composition_capabilities")
        if not capabilities.supports_opacity and any(
            item.visible and item.transform.opacity != 1.0 for item in composition.elements
        ):
            raise CompositionRenderUnsupportedError("Renderer does not support element opacity.")
        if not capabilities.supports_rotation and any(
            item.visible and item.transform.rotation_degrees != 0.0 for item in composition.elements
        ):
            raise CompositionRenderUnsupportedError("Renderer does not support element rotation.")
        if set(asset_paths) != required_ids:
            raise CompositionRenderBridgeError(
                "asset_paths must contain exactly the visible composition asset IDs."
            )
        resolved_paths = {}
        for asset_id, value in asset_paths.items():
            path = Path(value).expanduser()
            if path.is_symlink() or not path.is_file():
                raise CompositionRenderBridgeError(
                    f"Composition asset '{asset_id}' is not a regular local file."
                )
            resolved_paths[asset_id] = path.resolve(strict=True)
        destination = Path(destination).expanduser()
        if not str(destination).strip():
            raise CompositionRenderBridgeError("destination must be a non-empty path.")
        adapter = self._adapters[engine_id]
        output = adapter.render_composition(
            composition,
            asset_paths=resolved_paths,
            destination=destination,
            output_format=output_format,
            on_progress=on_progress,
            cancel=cancel,
        )
        output = Path(output)
        if output.resolve() != destination.resolve():
            raise CompositionRenderBridgeError(
                "Composition renderer must write to the exact requested destination."
            )
        if not output.is_file() or output.stat().st_size <= 0:
            raise CompositionRenderBridgeError(
                "Composition renderer returned a missing or empty output."
            )
        return output
