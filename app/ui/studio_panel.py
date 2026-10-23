from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, Optional

from app.cache.video_cache import VideoCache
from app.core.async_bridge import AsyncBridge
from app.core.config import AppConfig
from app.core.logger import get_logger
from app.tts.manager import TTSManager
from app.ui.studio_audio_tab import AudioTab
from app.ui.studio_context import StudioContext
from app.ui.studio_produce_tab import ProduceTab
from app.ui.studio_scenes_tab import ScenesTab
from app.ui.studio_video_tab import VideoTab
from app.ui.voice_panel import VoicePanel

logger = get_logger("ui.studio")

# Sidebar entry -> notebook tab.
SECTION_TABS: Dict[str, str] = {
    "Voice": "voice",
    "Audio": "audio",
    "Timeline": "scenes",
    "Video": "video",
    "Produce": "produce",
}

_PROJECT_POLL_MS = 700


class StudioPanel(ttk.Frame):
    """One workspace for the whole production: Voice & Narration (the existing
    Voice page, unchanged), Audio (music, mix, waveform), Scenes (media,
    timing, timeline), Video (format) and Produce (end-to-end run). The
    sidebar entries Voice / Audio / Timeline / Video / Produce all open this
    panel on the matching tab, and the tabs are also clickable directly."""

    SECTION_NAMES = tuple(SECTION_TABS)

    def __init__(
        self,
        master: tk.Widget,
        tts_manager: TTSManager,
        async_bridge: AsyncBridge,
        config: AppConfig,
        palette: dict,
        script_source,
        on_status=None,
    ) -> None:
        super().__init__(master, style="App.TFrame")
        self._palette = palette
        self._on_status = on_status or (lambda text: None)
        self._poll_job: Optional[str] = None

        self._style_notebook(palette)
        self._notebook = ttk.Notebook(self, style="Studio.TNotebook")
        self._notebook.pack(fill="both", expand=True)

        self.voice = VoicePanel(
            self._notebook, tts_manager=tts_manager, async_bridge=async_bridge, config=config,
            palette=palette, on_status=self._on_status, script_source=script_source,
        )
        video_cache = VideoCache(config.video_cache_dir)
        self.ctx = StudioContext(
            config=config, bridge=async_bridge, palette=palette, ffmpeg=self.voice.ffmpeg,
            video_cache=video_cache, script=script_source, voice=self.voice, on_status=self._on_status,
        )
        self.ctx.load()

        self.audio_tab = AudioTab(self._notebook, self.ctx)
        self.scenes_tab = ScenesTab(self._notebook, self.ctx)
        self.video_tab = VideoTab(self._notebook, self.ctx)
        self.produce_tab = ProduceTab(self._notebook, self.ctx)
        self.ctx.export_audio = self.produce_tab.export_audio_dialog
        self.ctx.refresh_scenes = self.scenes_tab.refresh

        self._tabs = {
            "voice": self.voice, "audio": self.audio_tab, "scenes": self.scenes_tab,
            "video": self.video_tab, "produce": self.produce_tab,
        }
        for key, label in (("voice", "Voice & Narration"), ("audio", "Audio & Music"),
                           ("scenes", "Scenes & Timeline"), ("video", "Video Settings"), ("produce", "Produce")):
            self._notebook.add(self._tabs[key], text=f"  {label}  ")
        self._notebook.bind("<<NotebookTabChanged>>", lambda _e: self._refresh_current())
        self._refresh_all()
        self._poll_project()

    # ------------------------------------------------------------------ navigation

    def show_section(self, name: str) -> None:
        key = SECTION_TABS.get(name)
        if key is None:
            return
        self._notebook.select(self._tabs[key])
        self._refresh_current()

    def _refresh_current(self) -> None:
        self._reload_if_project_changed()
        current = self._notebook.nametowidget(self._notebook.select())
        refresh = getattr(current, "refresh", None)
        if refresh is not None and current is not self.voice:
            refresh()

    def _refresh_all(self) -> None:
        for key in ("audio", "scenes", "video", "produce"):
            self._tabs[key].refresh()

    def _reload_if_project_changed(self) -> None:
        """A different project was opened/created on the Script page: reload
        the studio settings stored in it."""
        if self.ctx.project_changed():
            self.ctx.load()
            self._refresh_all()

    def _poll_project(self) -> None:
        try:
            if not self.ctx.produce_running() and self.ctx.project_changed():
                self._reload_if_project_changed()
        except tk.TclError:
            return
        self._poll_job = self.after(_PROJECT_POLL_MS, self._poll_project)

    # ------------------------------------------------------------------ theme / lifecycle

    def _style_notebook(self, palette: dict) -> None:
        style = ttk.Style(self)
        style.configure("Studio.TNotebook", background=palette["bg"], borderwidth=0, tabmargins=(12, 8, 12, 0))
        style.configure("Studio.TNotebook.Tab", background=palette["bg_alt"], foreground=palette["fg"],
                        padding=(10, 6), borderwidth=0)
        style.map("Studio.TNotebook.Tab",
                  background=[("selected", palette["accent"]), ("active", palette["border"])],
                  foreground=[("selected", "#ffffff")])

    def apply_theme(self, palette: dict) -> None:
        self._palette = palette
        self.ctx.palette = palette
        self._style_notebook(palette)
        for tab in self._tabs.values():
            apply = getattr(tab, "apply_theme", None)
            if apply is not None:
                apply(palette)

    def confirm_close(self) -> bool:
        if self.produce_tab.running:
            if not messagebox.askyesno(
                "Production In Progress",
                "A production is still running. Finished narration and scene clips are kept, "
                "but the video will not be completed.\n\nClose anyway?",
            ):
                return False
        return self.voice.confirm_close()

    def shutdown(self) -> None:
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self.produce_tab._token is not None:
            self.produce_tab._token.cancel()
        self.audio_tab.shutdown()
        self.voice.shutdown()