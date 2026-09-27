from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List


class Sidebar(ttk.Frame):
    NAV_ITEMS: List[str] = [
        "Dashboard",
        "Projects",
        "Script",
        "Voice",
        "Audio",
        "Timeline",
        "Subtitles",
        "Settings",
    ]

    def __init__(self, master: tk.Widget, on_select: Callable[[str], None]):
        super().__init__(master, style="Sidebar.TFrame", width=200)
        self.pack_propagate(False)
        self._on_select = on_select
        self._buttons: Dict[str, ttk.Button] = {}
        self._active = self.NAV_ITEMS[0]

        header = ttk.Label(self, text="  NAVIGATION", style="SidebarMuted.TLabel")
        header.pack(fill="x", pady=(16, 8), padx=4)

        for item in self.NAV_ITEMS:
            btn = ttk.Button(
                self,
                text=item,
                style="Nav.TButton",
                command=lambda name=item: self._handle_click(name),
            )
            btn.pack(fill="x", padx=6, pady=1)
            self._buttons[item] = btn

        self.set_active(self._active)

    def _handle_click(self, name: str) -> None:
        self.set_active(name)
        self._on_select(name)

    def set_active(self, name: str) -> None:
        if name not in self._buttons:
            return
        for item, btn in self._buttons.items():
            btn.configure(style="NavActive.TButton" if item == name else "Nav.TButton")
        self._active = name