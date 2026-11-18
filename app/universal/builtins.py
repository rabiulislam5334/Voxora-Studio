"""Explicit composition root for built-in Universal Core engines."""
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


def _checked_descriptor(ffmpeg_tool, *, probe_availability: bool) -> tuple[EngineDescriptor, bool]:
    descriptor = FFmpegSegmentAdapter.build_descriptor()
    try:
        status = ffmpeg_tool.detect() if probe_availability else ffmpeg_tool.status
        if status is None:
            available = False
            reason = "FFmpeg availability has not been verified; run detection before registration."
        else:
            available = bool(status.available)
            reason = "" if available else str(status.message or "FFmpeg is unavailable.")
    except Exception as exc:
        available = False
        reason = f"FFmpeg availability check failed: {exc}"

    if available:
        return descriptor, True
    return replace(descriptor, available=False, unavailable_reason=reason), False


def build_builtin_engine_runtime_registry(
    ffmpeg_tool: Optional[FFmpegTool] = None,
    *,
    probe_availability: bool = False,
) -> EngineRuntimeRegistry:
    """Build a deterministic registry from explicitly supported built-ins.

    The default path consumes cached dependency status and never starts a
    subprocess. Set probe_availability=True only at an explicit setup boundary.
    Adapter construction remains lazy until exact engine resolution.
    """
    tool = ffmpeg_tool if ffmpeg_tool is not None else _default_ffmpeg_tool()
    descriptor, available = _checked_descriptor(tool, probe_availability=probe_availability)

    registry = EngineRuntimeRegistry(EngineRegistry((descriptor,)))
    if available:
        registry.register(descriptor, lambda: FFmpegSegmentAdapter(tool))
    return registry
