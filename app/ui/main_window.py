from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional

from app.core import constants
from app.core.async_bridge import AsyncBridge
from app.core.config import get_config
from app.core.logger import get_logger
from app.tts.edge_tts_provider import EdgeTTSProvider
from app.tts.manager import TTSManager
from app.ui.sidebar import Sidebar
from app.ui.status_bar import StatusBar
from app.ui.theme import apply_theme
from app.ui.script_panel import ScriptPanel
from app.ui.voice_panel import VoicePanel

logger = get_logger("ui.main_window")

_POLL_INTERVAL_MS = 120

_PAGE_DESCRIPTIONS: Dict[str, str] = {
    "Dashboard": "Overview of your projects and current TTS provider status.",
    "Projects": "The project browser will be implemented in a later phase.",
    "Audio": "Audio preview and processing tools will be implemented in Phase 6.",
    "Timeline": "The scene/audio timeline will be implemented in Phase 12.",
    "Subtitles": "SRT subtitle generation will be implemented in Phase 8.",
    "Settings": "Application and provider settings will be implemented incrementally.",
}


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = get_config()
        self.style = ttk.Style(root)
        self.theme_name = self.config.default_theme
        self.palette = apply_theme(self.style, self.theme_name)

        self.tts_manager = TTSManager()
        self.tts_manager.register(EdgeTTSProvider(), set_active=True)
        self.async_bridge = AsyncBridge()

        self._pages: Dict[str, ttk.Frame] = {}
        self._current_page: Optional[str] = None
        self._unsaved_changes = False
        self._project_name = "Untitled Project"

        self._build_window()
        self._build_layout()
        self._show_page("Dashboard")
        self._poll_async_bridge()

        logger.info("Main window initialized")

    # ---------- window setup ----------

    def _build_window(self) -> None:
        self.root.title(constants.APP_NAME)
        self.root.geometry(constants.DEFAULT_WINDOW_SIZE)
        self.root.minsize(constants.MIN_WINDOW_WIDTH, constants.MIN_WINDOW_HEIGHT)
        self.root.configure(background=self.palette["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_top_bar()

        self.sidebar = Sidebar(self.root, on_select=self._show_page)
        self.sidebar.grid(row=1, column=0, sticky="ns")

        self.content = ttk.Frame(self.root, style="App.TFrame")
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.status_bar = StatusBar(self.root)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")

        self._build_pages()

    def _build_top_bar(self) -> None:
        top_bar = ttk.Frame(self.root, style="TopBar.TFrame")
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        top_bar.columnconfigure(1, weight=1)

        ttk.Label(top_bar, text=constants.APP_NAME, style="TopBarTitle.TLabel").grid(
            row=0, column=0, padx=16, pady=10, sticky="w"
        )

        self.project_label = ttk.Label(top_bar, text=self._project_name, style="TopBarMuted.TLabel")
        self.project_label.grid(row=0, column=1, sticky="w")

        ttk.Button(
            top_bar, text="Toggle Theme", style="Nav.TButton", command=self._toggle_theme
        ).grid(row=0, column=2, padx=(0, 8), pady=10)

        ttk.Button(
            top_bar, text="Export", style="Primary.TButton", command=self._on_export
        ).grid(row=0, column=3, padx=(0, 16), pady=10)

    def _build_pages(self) -> None:
        for name, description in _PAGE_DESCRIPTIONS.items():
            self._pages[name] = self._build_placeholder_page(name, description)
        self._pages["Voice"] = self._build_voice_page()
        self._pages["Script"] = self._build_script_page()

    def _build_voice_page(self) -> VoicePanel:
        panel = VoicePanel(
            self.content,
            tts_manager=self.tts_manager,
            async_bridge=self.async_bridge,
            config=self.config,
            palette=self.palette,
            on_status=self.status_bar.set_text,
        )
        panel.grid(row=0, column=0, sticky="nsew")
        return panel

    def _build_script_page(self) -> ScriptPanel:
        panel = ScriptPanel(
            self.content,
            config=self.config,
            palette=self.palette,
            on_status=self.status_bar.set_text,
        )
        panel.grid(row=0, column=0, sticky="nsew")
        return panel

    def _build_placeholder_page(self, name: str, description: str) -> ttk.Frame:
        page = ttk.Frame(self.content, style="App.TFrame")
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)

        ttk.Label(page, text=name, style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=24, pady=(24, 4)
        )
        ttk.Label(
            page, text=description, style="Muted.TLabel", wraplength=640, justify="left"
        ).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 16))

        if name == "Dashboard":
            self._populate_dashboard(page)

        return page

    def _populate_dashboard(self, page: ttk.Frame) -> None:
        actions = ttk.Frame(page, style="App.TFrame")
        actions.grid(row=2, column=0, sticky="w", padx=24, pady=(0, 24))

        ttk.Button(
            actions, text="New Project", style="Primary.TButton", command=self._on_new_project
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(
            actions, text="Open Project", style="Nav.TButton", command=self._on_open_project
        ).grid(row=0, column=1)

        cards = ttk.Frame(page, style="App.TFrame")
        cards.grid(row=3, column=0, sticky="w", padx=24, pady=(0, 24))

        card_info = [
            ("Projects", "0 saved locally"),
            ("Recent Project", "None yet"),
            ("TTS Provider", self.tts_manager.get_provider_name()),
            ("Application Status", "Ready"),
        ]
        for i, (title, value) in enumerate(card_info):
            card = ttk.Frame(cards, style="Card.TFrame", padding=12)
            card.grid(row=0, column=i, padx=(0, 12), sticky="n")
            ttk.Label(card, text=title, style="Muted.TLabel").pack(anchor="w")
            ttk.Label(card, text=value, style="App.TLabel").pack(anchor="w", pady=(4, 0))

    # ---------- navigation ----------

    def _show_page(self, name: str) -> None:
        if name not in self._pages:
            logger.warning("Unknown page requested: %s", name)
            return
        self._pages[name].tkraise()
        self._current_page = name
        self.status_bar.set_text(name)
        logger.debug("Navigated to page: %s", name)

    # ---------- background task polling ----------

    def _poll_async_bridge(self) -> None:
        self.async_bridge.poll()
        self.root.after(_POLL_INTERVAL_MS, self._poll_async_bridge)

    # ---------- actions ----------

    def _on_new_project(self) -> None:
        self.status_bar.set_text("New project — full flow implemented in a later phase.")

    def _on_open_project(self) -> None:
        self.status_bar.set_text("Open project — full flow implemented in a later phase.")

    def _on_export(self) -> None:
        self.status_bar.set_text("Export — implemented once the audio/video pipelines exist.")

    def _toggle_theme(self) -> None:
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.palette = apply_theme(self.style, self.theme_name)
        self.root.configure(background=self.palette["bg"])

        # ttk widgets restyle themselves automatically via the style names
        # they were created with. Only pages holding raw tk widgets (e.g.
        # VoicePanel's tk.Text) need an explicit recolor -- rebuilding
        # every page from scratch would wipe in-progress script text.
        for page in self._pages.values():
            if hasattr(page, "apply_theme"):
                page.apply_theme(self.palette)

        logger.info("Theme switched to %s", self.theme_name)

    def _on_close(self) -> None:
        for page in self._pages.values():
            if hasattr(page, "confirm_close") and not page.confirm_close():
                logger.info("Close cancelled by page veto (e.g. unsaved audio)")
                return

        if self._unsaved_changes:
            logger.info("Closing with unsaved changes (autosave/prompt lands in a later phase)")

        for page in self._pages.values():
            if hasattr(page, "shutdown"):
                page.shutdown()

        logger.info("Shutting down background TTS worker")
        self.async_bridge.shutdown()
        logger.info("Application closing")
        self.root.destroy()