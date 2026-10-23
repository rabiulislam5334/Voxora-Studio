from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Dict, List, Optional

from app.audio.ffmpeg_tool import FFmpegTool
from app.cache.video_cache import VideoCache
from app.core.async_bridge import AsyncBridge
from app.core.config import AppConfig
from app.models.scene import Scene
from app.studio.models import StudioState


class StudioContext:
    """State and services shared by the Studio tabs: the studio settings of
    the open project, background-task helper, FFmpeg, caches and the two
    neighbouring pages. Tabs never reach into each other; they go through
    this object."""

    def __init__(
        self,
        config: AppConfig,
        bridge: AsyncBridge,
        palette: dict,
        ffmpeg: FFmpegTool,
        video_cache: VideoCache,
        script,
        voice,
        on_status: Callable[[str], None],
    ) -> None:
        self.config = config
        self.bridge = bridge
        self.palette = palette
        self.ffmpeg = ffmpeg
        self.video_cache = video_cache
        self.script = script
        self.voice = voice
        self.on_status = on_status
        self.state = StudioState()
        self.known_durations: Dict[str, float] = {}   # real narration length per scene, from the last run
        self.export_audio: Callable[[], None] = lambda: None   # set by StudioPanel
        self.refresh_scenes: Callable[[], None] = lambda: None  # set by StudioPanel
        self._project_ref = None

    # ---- project state ----

    def project(self):
        return self.script.get_project()

    def scenes(self) -> List[Scene]:
        return self.script.get_scenes()

    def produce_running(self) -> bool:
        return bool(getattr(self.voice, "is_busy", lambda: False)())

    def project_changed(self) -> bool:
        return self.project() is not self._project_ref

    def load(self) -> None:
        project = self.project()
        self._project_ref = project
        self.state = StudioState.from_project_settings(project.settings)
        self.state.prune_scenes(s.id for s in project.scenes)
        self.known_durations.clear()

    def commit(self) -> None:
        """Store the studio settings in the project (and mark it unsaved)
        only when something actually changed."""
        project = self.project()
        new = self.state.to_dict()
        if project.settings.get("studio") != new:
            project.settings["studio"] = new
            self.script.mark_project_dirty()

    # ---- background work ----

    def run_bg(self, func: Callable, *args, on_success=None, on_error=None) -> None:
        """Run a blocking function on a worker thread; callbacks run on the Tk thread."""
        self.bridge.run_coroutine(
            asyncio.to_thread(func, *args),
            on_success=on_success,
            on_error=on_error or (lambda exc: self.on_status(f"Error: {exc}")),
        )


def fmt_seconds(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    total = max(0, int(round(seconds)))
    return f"{total // 60:02d}:{total % 60:02d}"


def short_name(path: Optional[str]) -> str:
    return Path(path).name if path else ""