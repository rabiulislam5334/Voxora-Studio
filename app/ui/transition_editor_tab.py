"""Desktop editor for project-wide transition timing and per-scene effects.

Transition overrides are stored in the existing forward-compatible video
settings extra payload. The editor never changes the legacy project schema.
"""
from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from app.core.timebase import seconds_to_ticks
from app.universal.transitions import (
    TRANSITION_EASINGS,
    TRANSITION_EFFECTS,
    TransitionSpec,
)

_STORE_KEY = "scene_transitions"
_STORE_VERSION = 1
_EFFECT_LABELS = {
    "crossfade": "Crossfade",
    "wipe_left": "Wipe Left",
    "wipe_right": "Wipe Right",
    "wipe_up": "Wipe Up",
    "wipe_down": "Wipe Down",
    "dip_to_color": "Dip to Color",
}
_LABEL_EFFECTS = {label: effect for effect, label in _EFFECT_LABELS.items()}


class TransitionEditorTab(ttk.Frame):
    """Configure global overlap timing and each scene's outgoing transition."""

    def __init__(self, master, ctx) -> None:
        super().__init__(master, style="App.TFrame", padding=16)
        self.ctx = ctx
        self._loading = False
        self._scene_ids = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="Transition Editor", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            self,
            text=("Set the project overlap duration, then customize the effect leaving "
                  "each scene. Changes are saved in the open .voxora project's Studio settings."),
            style="Muted.TLabel", wraplength=1050,
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        timing = ttk.LabelFrame(self, text="Project Timeline", padding=10)
        timing.grid(row=2, column=0, sticky="new", pady=(0, 12))
        timing.columnconfigure(5, weight=1)
        ttk.Label(timing, text="Transition mode").grid(row=0, column=0, sticky="w")
        self._mode_var = tk.StringVar()
        self._mode = ttk.Combobox(
            timing, textvariable=self._mode_var, state="readonly", width=14,
            values=("Cut", "Overlap"),
        )
        self._mode.grid(row=0, column=1, padx=(8, 18), sticky="w")
        self._mode.bind("<<ComboboxSelected>>", self._on_mode)
        ttk.Label(timing, text="Overlap duration (seconds)").grid(row=0, column=2, sticky="w")
        self._duration_var = tk.StringVar()
        self._duration = ttk.Spinbox(
            timing, from_=0.1, to=3.0, increment=0.1,
            textvariable=self._duration_var, width=8,
        )
        self._duration.grid(row=0, column=3, padx=8, sticky="w")
        self._duration.bind("<FocusOut>", self._on_duration)
        self._duration.bind("<Return>", self._on_duration)
        ttk.Button(timing, text="Apply Timing", style="Primary.TButton",
                   command=self._on_duration).grid(row=0, column=4, padx=(8, 0))
        ttk.Label(
            timing,
            text="Current renderer uses one shared overlap duration for all scene boundaries.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)
        left = ttk.Frame(body, style="App.TFrame", padding=(0, 0, 10, 0))
        right = ttk.Frame(body, style="App.TFrame", padding=(10, 0, 0, 0))
        body.add(left, weight=2)
        body.add(right, weight=3)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Scene Boundaries", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self._tree = ttk.Treeview(
            left, columns=("effect", "duration"), show="headings",
            selectmode="browse", height=14,
        )
        for col, label, width in (
            ("effect", "Outgoing Effect", 150), ("duration", "Overlap", 80),
        ):
            self._tree.heading(col, text=label)
            self._tree.column(col, width=width, anchor="center")
        self._tree.grid(row=1, column=0, sticky="nsew")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        right.columnconfigure(1, weight=1)
        ttk.Label(right, text="Selected Boundary", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        self._scene_label = ttk.Label(right, text="Select a scene boundary", style="Muted.TLabel")
        self._scene_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(right, text="Effect").grid(row=2, column=0, sticky="w", pady=5)
        self._effect_var = tk.StringVar()
        self._effect = ttk.Combobox(
            right, textvariable=self._effect_var, state="readonly", width=22,
            values=tuple(_EFFECT_LABELS.values()),
        )
        self._effect.grid(row=2, column=1, sticky="ew", pady=5)
        self._effect.bind("<<ComboboxSelected>>", self._on_field)
        ttk.Label(right, text="Easing").grid(row=3, column=0, sticky="w", pady=5)
        self._easing_var = tk.StringVar()
        self._easing = ttk.Combobox(
            right, textvariable=self._easing_var, state="readonly", width=22,
            values=TRANSITION_EASINGS,
        )
        self._easing.grid(row=3, column=1, sticky="ew", pady=5)
        self._easing.bind("<<ComboboxSelected>>", self._on_field)
        ttk.Label(right, text="Dip color (hex)").grid(row=4, column=0, sticky="w", pady=5)
        self._color_var = tk.StringVar(value="#000000")
        self._color = ttk.Entry(right, textvariable=self._color_var, width=12)
        self._color.grid(row=4, column=1, sticky="w", pady=5)
        self._color.bind("<FocusOut>", self._on_field)
        ttk.Button(right, text="Apply to Scene", style="Primary.TButton",
                   command=self._apply_scene).grid(row=5, column=1, sticky="w", pady=(10, 0))
        ttk.Button(right, text="Use Project Default", style="Secondary.TButton",
                   command=self._reset_scene).grid(row=6, column=1, sticky="w", pady=(6, 0))
        self._status = tk.StringVar(value="Open a project to configure transitions.")
        ttk.Label(self, textvariable=self._status, style="Muted.TLabel").grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )

    def _store(self) -> dict:
        raw = self.ctx.state.video.extra.get(_STORE_KEY, {})
        if not isinstance(raw, dict) or raw.get("version", _STORE_VERSION) != _STORE_VERSION:
            raise ValueError("Scene transition settings are malformed or from an unsupported version.")
        transitions = raw.get("scenes", {})
        if not isinstance(transitions, dict):
            raise ValueError("Scene transition map must be an object.")
        return copy.deepcopy(raw)

    def _write_store(self, store: dict) -> None:
        if self.ctx.state.read_only:
            raise ValueError("This project's Studio settings are read-only in this Voxora version.")
        self.ctx.state.video.extra[_STORE_KEY] = store
        self.ctx.commit()
        self._status.set("Transition settings saved to the open project.")

    def _resolved(self, scene_id: str) -> TransitionSpec:
        store = self._store()
        raw = store.get("scenes", {}).get(scene_id)
        if raw is not None:
            return TransitionSpec.from_dict(raw)
        video = self.ctx.state.video
        if video.transition == "cut":
            return TransitionSpec.cut()
        return TransitionSpec(effect="crossfade", duration_ticks=seconds_to_ticks(video.transition_s))

    def refresh(self) -> None:
        self._loading = True
        try:
            scenes = self.ctx.scenes()
            self._scene_ids = [scene.id for scene in scenes]
            video = self.ctx.state.video
            self._mode_var.set("Cut" if video.transition == "cut" else "Overlap")
            self._duration_var.set(f"{video.transition_s:g}")
            self._duration.state(["!disabled"] if video.transition == "crossfade" else ["disabled"])
            self._tree.delete(*self._tree.get_children())
            for scene in scenes[:-1]:
                spec = self._resolved(scene.id)
                self._tree.insert(
                    "", "end", iid=scene.id,
                    values=(spec.effect.replace("_", " ").title(),
                            "0" if spec.effect == "cut" else f"{video.transition_s:g}s"),
                )
            selected = self._tree.selection()
            if selected and self._tree.exists(selected[0]):
                self._tree.selection_set(selected[0])
            elif self._tree.get_children():
                self._tree.selection_set(self._tree.get_children()[0])
        except Exception as exc:
            self._status.set(f"Cannot load transition settings: {exc}")
        finally:
            self._loading = False
        self._on_select()

    def _selected_id(self):
        selection = self._tree.selection()
        return selection[0] if selection else None

    def _on_select(self, _event=None) -> None:
        scene_id = self._selected_id()
        enabled = scene_id is not None and self.ctx.state.video.transition == "crossfade"
        for widget in (self._effect, self._easing, self._color):
            widget.configure(state="readonly" if widget is self._effect or widget is self._easing else "normal")
            if not enabled:
                widget.state(["disabled"])
            else:
                widget.state(["!disabled"])
        if scene_id is None:
            self._scene_label.configure(text="No outgoing scene boundary selected.")
            return
        scenes = {scene.id: scene for scene in self.ctx.scenes()}
        scene = scenes.get(scene_id)
        self._scene_label.configure(text=f"After Scene {scene.order + 1}: {scene.title}" if scene else scene_id)
        try:
            spec = self._resolved(scene_id)
            self._effect_var.set(_EFFECT_LABELS.get(spec.effect, "Crossfade"))
            self._easing_var.set(spec.easing)
            rgb = spec.color_rgb or (0, 0, 0)
            self._color_var.set("#%02X%02X%02X" % rgb)
        except Exception as exc:
            self._status.set(f"Invalid scene transition: {exc}")

    def _on_mode(self, _event=None) -> None:
        if self._loading:
            return
        video = self.ctx.state.video
        video.transition = "cut" if self._mode_var.get() == "Cut" else "crossfade"
        self.ctx.commit()
        self.refresh()

    def _on_duration(self, _event=None) -> None:
        if self._loading or self.ctx.state.video.transition != "crossfade":
            return
        try:
            value = float(self._duration_var.get())
            if not 0.1 <= value <= 3.0:
                raise ValueError("Overlap duration must be between 0.1 and 3.0 seconds.")
        except ValueError as exc:
            messagebox.showerror("Invalid duration", str(exc), parent=self)
            self._duration_var.set(f"{self.ctx.state.video.transition_s:g}")
            return
        self.ctx.state.video.transition_s = value
        self.ctx.commit()
        self.refresh()

    def _on_field(self, _event=None) -> None:
        if self._loading:
            return
        self._apply_scene()

    def _apply_scene(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None or self.ctx.state.video.transition != "crossfade":
            return
        effect = _LABEL_EFFECTS.get(self._effect_var.get())
        easing = self._easing_var.get()
        try:
            color = None
            if effect == "dip_to_color":
                raw = self._color_var.get().strip()
                if len(raw) != 7 or not raw.startswith("#"):
                    raise ValueError("Dip color must be a six-digit hex color such as #000000.")
                color = tuple(int(raw[index:index + 2], 16) for index in (1, 3, 5))
            spec = TransitionSpec(
                effect=effect,
                duration_ticks=seconds_to_ticks(self.ctx.state.video.transition_s),
                easing=easing,
                color_rgb=color,
            )
            store = self._store()
            store["version"] = _STORE_VERSION
            store.setdefault("scenes", {})[scene_id] = spec.to_dict()
            self._write_store(store)
            self.refresh()
            if self._tree.exists(scene_id):
                self._tree.selection_set(scene_id)
                self._on_select()
        except (ValueError, TypeError) as exc:
            messagebox.showerror("Transition not applied", str(exc), parent=self)

    def _reset_scene(self) -> None:
        scene_id = self._selected_id()
        if scene_id is None:
            return
        try:
            store = self._store()
            store.setdefault("scenes", {}).pop(scene_id, None)
            self._write_store(store)
            self.refresh()
            if self._tree.exists(scene_id):
                self._tree.selection_set(scene_id)
                self._on_select()
        except ValueError as exc:
            messagebox.showerror("Transition not reset", str(exc), parent=self)
