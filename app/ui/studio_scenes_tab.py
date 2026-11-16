from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import List, Optional

from app.core.constants import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from app.core.logger import get_logger
from app.studio.models import MOTIONS, FITS, SceneVideo
from app.studio.previews import make_thumbnail
from app.studio.timing import SceneTimingInput, compute_timeline
from app.studio.validation import media_kind_from_extension
from app.text.wordcount import count_words, estimate_duration_seconds
from app.ui.studio_context import StudioContext, fmt_ticks, short_name, timeline_bounds

logger = get_logger("ui.studio.scenes")

_DEFAULT = "Project default"
_TL_W, _TL_H = 900, 58


class ScenesTab(ttk.Frame):
    """Scene media + timing: assign an image or video to each script scene,
    choose its duration/motion/fit, see a thumbnail, and a proportional
    timeline of the whole video (real narration lengths after a production
    run, word-count estimates before)."""

    def __init__(self, master: tk.Widget, ctx: StudioContext) -> None:
        super().__init__(master, style="App.TFrame")
        self._ctx = ctx
        self._thumb: Optional[tk.PhotoImage] = None
        self._loading = False
        self._scene_ids: List[str] = []
        self._build()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="Scenes follow the order of your script. Assign an image or video to each scene.",
                  style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 4))

        left = ttk.Frame(self, style="App.TFrame")
        left.grid(row=1, column=0, sticky="nsew", padx=(16, 8))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        cols = ("num", "title", "media", "status", "length", "motion")
        self._tree = ttk.Treeview(left, columns=cols, show="headings", style="Scene.Treeview", selectmode="browse")
        for col, text, width in (("num", "#", 34), ("title", "Scene", 150), ("media", "Media", 150),
                                 ("status", "Status", 80), ("length", "Length", 90), ("motion", "Motion", 80)):
            self._tree.heading(col, text=text)
            self._tree.column(col, width=width, anchor="w" if col in ("title", "media") else "center")
        self._tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_select())

        right = ttk.Frame(self, style="App.TFrame")
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16))
        self._canvas = tk.Canvas(right, width=320, height=180, highlightthickness=1,
                                 background=self._ctx.palette["field_bg"], highlightbackground=self._ctx.palette["border"])
        self._canvas.grid(row=0, column=0, columnspan=3, sticky="w")
        self._canvas.create_text(160, 90, text="No scene selected", fill=self._ctx.palette["fg_muted"], tags="hint")
        self._media_label = ttk.Label(right, text="", style="Muted.TLabel", wraplength=320, justify="left")
        self._media_label.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 6))
        self._assign_btn = ttk.Button(right, text="Assign Media...", style="Primary.TButton", command=self._on_assign, state="disabled")
        self._assign_btn.grid(row=2, column=0, sticky="w")
        self._clear_btn = ttk.Button(right, text="Clear", style="Secondary.TButton", command=self._on_clear, state="disabled")
        self._clear_btn.grid(row=2, column=1, sticky="w", padx=6)

        ttk.Label(right, text="Duration (s, 0 = automatic):", style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self._dur_var = tk.StringVar(value="0")
        self._dur = ttk.Spinbox(right, from_=0, to=600, increment=0.5, textvariable=self._dur_var, width=8,
                                command=self._on_field_change)
        self._dur.grid(row=3, column=2, sticky="w", pady=(10, 0))
        self._dur.bind("<KeyRelease>", lambda _e: self._on_field_change())
        ttk.Label(right, text="Motion (images):", style="Muted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._motion_var = tk.StringVar(value=_DEFAULT)
        self._motion = ttk.Combobox(right, textvariable=self._motion_var, state="readonly", style="App.TCombobox",
                                    width=16, values=[_DEFAULT, *MOTIONS])
        self._motion.grid(row=4, column=2, sticky="w", pady=(6, 0))
        self._motion.bind("<<ComboboxSelected>>", lambda _e: self._on_field_change())
        ttk.Label(right, text="Fit:", style="Muted.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._fit_var = tk.StringVar(value=_DEFAULT)
        self._fit = ttk.Combobox(right, textvariable=self._fit_var, state="readonly", style="App.TCombobox",
                                 width=16, values=[_DEFAULT, *FITS])
        self._fit.grid(row=5, column=2, sticky="w", pady=(6, 0))
        self._fit.bind("<<ComboboxSelected>>", lambda _e: self._on_field_change())
        ttk.Label(right, text="fill = crop to cover the frame, fit = letterbox (black bars).",
                  style="Muted.TLabel", wraplength=320).grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 0))

        ttk.Label(self, text="Timeline", style="SectionTitle.TLabel").grid(row=2, column=0, sticky="w", padx=16, pady=(8, 2))
        self._timeline = tk.Canvas(self, width=_TL_W, height=_TL_H, highlightthickness=1,
                                   background=self._ctx.palette["field_bg"], highlightbackground=self._ctx.palette["border"])
        self._timeline.grid(row=3, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 4))
        self._summary = ttk.Label(self, text="", style="Muted.TLabel")
        self._summary.grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 10))
        for widget in (self._dur, self._motion, self._fit):
            widget.state(["disabled"])

    # ------------------------------------------------------------------ data

    def refresh(self) -> None:
        keep = self._selected_id()
        scenes = self._ctx.scenes()
        self._scene_ids = [s.id for s in scenes]
        video = self._ctx.state.video
        self._tree.delete(*self._tree.get_children())
        timings = self._estimate(scenes)
        slots = {slot.scene_id: slot for slot in timings.slots}
        for scene in scenes:
            setting = video.scene(scene.id)
            if not setting.media_path:
                status = "none"
            elif Path(setting.media_path).is_file():
                status = "ok"
            else:
                status = "MISSING"
            known = scene.id in self._ctx.known_durations
            slot = slots.get(scene.id)
            length = "" if slot is None else f"{fmt_ticks(slot.slot_ticks)}{'' if known or not scene.text.strip() else ' est.'}"
            self._tree.insert("", "end", iid=scene.id, values=(
                scene.order + 1, scene.title, short_name(setting.media_path) or "-", status, length,
                setting.motion or _DEFAULT))
        if keep and self._tree.exists(keep):
            self._tree.selection_set(keep)
        self._on_select()
        self._draw_timeline(scenes, timings)

    def _estimate(self, scenes):
        video = self._ctx.state.video
        inputs = []
        for scene in scenes:
            narration = None
            if scene.text.strip():
                narration = self._ctx.known_durations.get(scene.id)
                if narration is None:
                    narration = estimate_duration_seconds(count_words(scene.text))
            inputs.append(SceneTimingInput(scene.id, narration, video.scene(scene.id).duration_s, 0.5))
        return compute_timeline(inputs, transition=video.transition, transition_s=video.transition_s,
                                default_duration_s=video.default_duration_s)

    def _draw_timeline(self, scenes, timings) -> None:
        canvas = self._timeline
        canvas.delete("all")
        total_ticks = timings.total_ticks
        palette = self._ctx.palette
        if total_ticks <= 0:
            canvas.create_text(_TL_W // 2, _TL_H // 2, text="No scenes yet", fill=palette["fg_muted"])
            self._summary.configure(text="")
            return
        video = self._ctx.state.video
        for scene, slot in zip(scenes, timings.slots):
            x0, x1 = timeline_bounds(slot.start_ticks, slot.slot_ticks, total_ticks, _TL_W - 2)
            x0 += 1
            x1 += 1
            path = video.scene(scene.id).media_path
            color = palette["fg_muted"] if not path else (palette["success"] if Path(path).is_file() else palette["error"])
            canvas.create_rectangle(x0, 6, max(x0 + 2, x1 - 1), _TL_H - 6, fill=color, outline=palette["border"])
            if x1 - x0 > 28:
                canvas.create_text((x0 + x1) / 2, _TL_H / 2, text=str(scene.order + 1), fill=palette["bg"])
        all_known = all(s.id in self._ctx.known_durations for s in scenes if s.text.strip())
        self._summary.configure(
            text=f"Total {fmt_ticks(total_ticks)}{'' if all_known else ' (estimate until narration is generated)'} - "
                 f"green = media ready, red = missing file, gray = none (black screen)")

    # ------------------------------------------------------------------ selection / editing

    def _selected_id(self) -> Optional[str]:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _on_select(self) -> None:
        scene_id = self._selected_id()
        self._loading = True
        enabled = scene_id is not None
        for btn in (self._assign_btn, self._clear_btn):
            btn.configure(state="normal" if enabled else "disabled")
        for widget in (self._dur, self._motion, self._fit):
            widget.state(["!disabled"] if enabled else ["disabled"])
        if scene_id is None:
            self._media_label.configure(text="")
            self._set_hint("No scene selected")
            self._loading = False
            return
        setting = self._ctx.state.video.scene(scene_id)
        self._dur_var.set(f"{setting.duration_s:g}" if setting.duration_s else "0")
        self._motion_var.set(setting.motion or _DEFAULT)
        self._fit_var.set(setting.fit or _DEFAULT)
        self._loading = False
        self._show_media(setting)

    def _show_media(self, setting: SceneVideo) -> None:
        self._thumb = None
        self._canvas.delete("all")
        if not setting.media_path:
            self._media_label.configure(text="No media - this scene renders as a black screen.")
            self._set_hint("No media")
            return
        path = Path(setting.media_path)
        if not path.is_file():
            self._media_label.configure(text=f"Missing file: {path}")
            self._set_hint("File not found")
            return
        self._media_label.configure(text=str(path))
        self._set_hint("Loading preview...")
        self._ctx.run_bg(make_thumbnail, self._ctx.ffmpeg, self._ctx.video_cache, path,
                         on_success=lambda png, p=str(path): self._show_thumb(png, p),
                         on_error=lambda e: self._set_hint("Preview unavailable"))

    def _show_thumb(self, png: Path, for_path: str) -> None:
        current = self._selected_id()
        if current is None or self._ctx.state.video.scene(current).media_path != for_path:
            return
        try:
            self._thumb = tk.PhotoImage(file=str(png))
        except tk.TclError:
            self._set_hint("Preview unavailable")
            return
        self._canvas.delete("all")
        self._canvas.create_image(160, 90, image=self._thumb, anchor="center")

    def _set_hint(self, text: str) -> None:
        self._canvas.delete("all")
        self._canvas.create_text(160, 90, text=text, fill=self._ctx.palette["fg_muted"])

    def _on_assign(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None:
            return
        patterns = " ".join(f"*{e}" for e in (*IMAGE_EXTENSIONS, *VIDEO_EXTENSIONS))
        path = filedialog.askopenfilename(title="Choose an image or video for this scene",
                                          filetypes=[("Images and videos", patterns), ("All files", "*.*")])
        if not path:
            return
        if media_kind_from_extension(path) not in ("image", "video"):
            self._ctx.on_status("That file type is not a supported image or video.")
            self._media_label.configure(text=f"Not an image or video: {Path(path).name}")
            return

        def check(p):
            return self._ctx.ffmpeg.probe(Path(p))

        def ok(info, p=path, sid=scene_id):
            if info.kind not in ("image", "video"):
                self._media_label.configure(text=f"Not an image or video: {Path(p).name}")
                return
            setting = self._ctx.state.video.scene(sid)
            setting.media_path = p
            self._ctx.state.video.set_scene(sid, setting)
            self._ctx.commit()
            self.refresh()

        self._ctx.run_bg(check, path, on_success=ok,
                         on_error=lambda e: self._media_label.configure(text=f"Could not use that file: {e}"))

    def _on_clear(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None:
            return
        setting = self._ctx.state.video.scene(scene_id)
        setting.media_path = None
        self._ctx.state.video.set_scene(scene_id, setting)
        self._ctx.commit()
        self.refresh()

    def _on_field_change(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None or self._loading:
            return
        setting = self._ctx.state.video.scene(scene_id)
        try:
            seconds = float(self._dur_var.get())
        except ValueError:
            return
        setting.duration_s = None if seconds <= 0 else max(0.5, min(3600.0, seconds))
        setting.motion = None if self._motion_var.get() == _DEFAULT else self._motion_var.get()
        setting.fit = None if self._fit_var.get() == _DEFAULT else self._fit_var.get()
        self._ctx.state.video.set_scene(scene_id, setting)
        self._ctx.commit()
        timings = self._estimate(self._ctx.scenes())
        self._draw_timeline(self._ctx.scenes(), timings)
        values = list(self._tree.item(scene_id, "values"))
        values[5] = setting.motion or _DEFAULT
        self._tree.item(scene_id, values=values)

    def apply_theme(self, palette: dict) -> None:
        for canvas in (self._canvas, self._timeline):
            canvas.configure(background=palette["field_bg"], highlightbackground=palette["border"])