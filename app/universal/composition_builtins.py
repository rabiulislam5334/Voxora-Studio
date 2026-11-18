"""Explicit composition-renderer composition root for built-in adapters."""
from __future__ import annotations

from app.universal.adapters.raster import RasterCompositionAdapter
from app.universal.composition_render_bridge import CompositionRenderBridge
from app.universal.raster_renderer import RasterCompositionRenderer


BUILTIN_COMPOSITION_RENDERER_IDS = ("raster",)


def build_builtin_composition_render_bridge(
    raster_renderer: RasterCompositionRenderer | None = None,
) -> CompositionRenderBridge:
    """Build the composition bridge without probing devices or external tools.

    Only the CPU raster renderer is registered. It renders still PNG frames;
    no video output or automatic fallback is implied.
    """
    adapter = RasterCompositionAdapter(raster_renderer)
    return CompositionRenderBridge({adapter.descriptor.engine_id: adapter})
