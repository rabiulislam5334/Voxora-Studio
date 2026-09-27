from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class StatusBar(ttk.Frame):
    def __init__(self, master: tk.Widget):
        super().__init__(master, style="StatusBar.TFrame")
        self._label = ttk.Label(self, text="Ready", style="Status.TLabel")
        self._label.pack(side="left", padx=12, pady=6)

        self._right_label = ttk.Label(self, text="", style="Status.TLabel")
        self._right_label.pack(side="right", padx=12, pady=6)

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def set_right_text(self, text: str) -> None:
        self._right_label.configure(text=text)