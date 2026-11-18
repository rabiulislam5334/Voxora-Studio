"""Explicit composition root for built-in Universal Core engines.

Only Voxora-owned engines are registered here. No package scanning, plugin
imports, model downloads, or renderer execution occurs during discovery.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from app.audio.ffmpeg_tool import FFmpegTool
from app.core.config import AppConfig
from app.core.settings_store import SettingsStore
from app.universal.adapters.ffmpeg import FFmpegSegmentAdapter
from app.universal.engines import EngineDescriptor, EngineRegistry
from app.universal.runtime import EngineRuntimeRegistry


BUILTIN_ENGINE_IDS = ("ffmpeg",)


def _default_ffmpeg_tool() -> FFmpegTool:
    """Create the lightweight FFmpeg service without probing the executable."""
    config = AppConfig()
    return FFmpegTool(SettingsStore(config.settings_file))


def _checked_descriptor(ffmpeg_tool: FFmpegTool) -> tuple[EngineDescriptor, bool]:
    descriptor = FFmpegSegmentAdapter.build_descriptor()
    try:
        status = ffmpeg_tool.detect()
        available = bool(status.available)
        reason = "" if available else str(status.message or "FFmpeg is unavailable.")
    except Exception as exc:
        available = False
        reason = f"FFmpeg availability check failed: {exc}"

    if available:
        return descriptor, True
    return replace(
        descriptor,
        available=False,
        unavailable_reason=reason or "FFmpeg is unavailable.",
    ), False


def build_builtin_engine_runtime_registry(
    ffmpeg_tool: Optional[FFmpegTool] = None,
) -> EngineRuntimeRegistry:
    """Build a deterministic runtime registry for explicitly supported engines.

    Dependency probing is performed once at this composition boundary. Adapter
    construction remains lazy: an available FFmpeg adapter is created only
    when the caller resolves the exact ffmpeg engine ID for execution.
    Unavailable engines remain visible as metadata and fail explicitly.
    """
    tool = ffmpeg_tool if ffmpeg_tool is not None else _default_ffmpeg_tool()
    descriptor, available = _checked_descriptor(tool)

    registry = EngineRuntimeRegistry(EngineRegistry((descriptor,)))
    if available:
        registry.register(descriptor, lambda: FFmpegSegmentAdapter(tool))
    return registry
