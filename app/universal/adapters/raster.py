"""Composition-renderer adapter for the CPU raster PNG backend."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Mapping, Optional
from app.universal.composition import SceneComposition
from app.universal.composition_render_bridge import CompositionRenderCapabilities
from app.universal.engines import EngineCapabilities, EngineDescriptor
from app.universal.raster_renderer import RasterCompositionRenderer

class RasterCompositionAdapter:
    """Expose the still-frame raster renderer through the composition bridge."""
    engine_id = "raster"

    @classmethod
    def build_descriptor(cls) -> EngineDescriptor:
        return EngineDescriptor(
            engine_id=cls.engine_id,
            display_name="CPU Raster Composition Renderer",
            version="1.0.0",
            capabilities=EngineCapabilities(
                scene_kinds=("composition",), asset_kinds=("image",),
                output_formats=("png",), requires_gpu=False,
                supports_draft_render=True, max_concurrent_jobs=1,
                estimated_memory_mb=256,
            ),
        )

    def __init__(self, renderer: Optional[RasterCompositionRenderer] = None) -> None:
        self._renderer = renderer or RasterCompositionRenderer()
        if not isinstance(self._renderer, RasterCompositionRenderer):
            raise TypeError("renderer must be a RasterCompositionRenderer")
        self.descriptor = self.build_descriptor()
        self.composition_capabilities = CompositionRenderCapabilities(
            output_formats=("png",), asset_kinds=("image",),
            supports_layers=True, supports_transforms=True,
            supports_opacity=True, supports_rotation=True,
        )

    def render_composition(
        self, composition: SceneComposition, *,
        asset_paths: Mapping[str, Path], destination: Path,
        output_format: str,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel=None,
    ) -> Path:
        if output_format != "png":
            raise ValueError("RasterCompositionAdapter only supports PNG output")
        result = self._renderer.render(
            composition, asset_paths=asset_paths, destination=destination,
            on_progress=on_progress, cancel=cancel,
        )
        return result.destination
