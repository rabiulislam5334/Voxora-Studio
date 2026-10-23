from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.studio.models import ASPECTS, FITS, MOTIONS, RESOLUTIONS, TRANSITIONS
from app.ui.studio_context import StudioContext


class VideoTab(ttk.Frame):
    """Output format and project-wide defaults for the video."""

    def __init__(self, master: tk.Widget, ctx: StudioContext) -> None:
        super().__init__(master, style="App.TFrame")
        self._ctx = ctx
        self._loading = False
        self._vars = {
            "aspect": tk.StringVar(), "resolution": tk.StringVar(), "fps": tk.StringVar(),
            "transition": tk.StringVar(), "transition_s": tk.StringVar(), "default_duration_s": tk.StringVar(),
            "default_motion": tk.StringVar(), "default_fit": tk.StringVar(),
        }
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text="Video format", style="SectionTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 8))
        rows = [
            ("aspect", "Aspect ratio", "combo", list(ASPECTS), "16:9 = YouTube landscape, 9:16 = Shorts/Reels"),
            ("resolution", "Resolution", "combo", list(RESOLUTIONS), "360p is a fast draft for checking timing"),
            ("fps", "Frame rate (fps)", "spin", (12, 60, 1), "24, 25 or 30 are typical"),
            ("transition", "Transition", "combo", list(TRANSITIONS), "crossfade overlaps neighbouring scenes"),
            ("transition_s", "Crossfade length (s)", "spin", (0.1, 3.0, 0.1), ""),
            ("default_duration_s", "Default scene length (s)", "spin", (0.5, 600, 0.5), "used for scenes with no narration"),
            ("default_motion", "Default image motion", "combo", list(MOTIONS), "applies to images only"),
            ("default_fit", "Default image fit", "combo", list(FITS), "fill = crop, fit = letterbox"),
        ]
        for i, (key, label, kind, options, hint) in enumerate(rows, start=1):
            ttk.Label(self, text=label, style="Muted.TLabel").grid(row=i, column=0, sticky="w", padx=(16, 8), pady=4)
            if kind == "combo":
                widget = ttk.Combobox(self, textvariable=self._vars[key], values=options, state="readonly",
                                      style="App.TCombobox", width=18)
                widget.bind("<<ComboboxSelected>>", lambda _e: self._changed())
            else:
                lo, hi, step = options
                widget = ttk.Spinbox(self, from_=lo, to=hi, increment=step, textvariable=self._vars[key], width=10,
                                     command=self._changed)
                widget.bind("<KeyRelease>", lambda _e: self._changed())
            widget.grid(row=i, column=1, sticky="w", pady=4)
            ttk.Label(self, text=hint, style="Muted.TLabel").grid(row=i, column=2, sticky="w", padx=12)
        self._size_label = ttk.Label(self, text="", style="App.TLabel")
        self._size_label.grid(row=len(rows) + 1, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 4))
        ttk.Label(self, text="Rendered scene clips are cached: changing audio, music or narration settings never re-renders "
                             "video, and only scenes whose picture settings changed are rendered again.",
                  style="Muted.TLabel", wraplength=760, justify="left").grid(
            row=len(rows) + 2, column=0, columnspan=3, sticky="w", padx=16)

    def refresh(self) -> None:
        video = self._ctx.state.video
        self._loading = True
        for key, var in self._vars.items():
            value = getattr(video, key)
            var.set(f"{value:g}" if isinstance(value, float) else str(value))
        self._loading = False
        self._update_size()

    def _update_size(self) -> None:
        w, h = self._ctx.state.video.size
        self._size_label.configure(text=f"Output size: {w} x {h} px")

    def _changed(self) -> None:
        if self._loading:
            return
        video = self._ctx.state.video
        for key in ("aspect", "resolution", "transition", "default_motion", "default_fit"):
            value = self._vars[key].get()
            if value:
                setattr(video, key, value)
        for key, cast in (("fps", int), ("transition_s", float), ("default_duration_s", float)):
            try:
                setattr(video, key, cast(float(self._vars[key].get())))
            except ValueError:
                pass
        video.fps = max(12, min(60, video.fps))
        video.transition_s = max(0.1, min(3.0, video.transition_s))
        video.default_duration_s = max(0.5, min(600.0, video.default_duration_s))
        self._ctx.commit()
        self._update_size()