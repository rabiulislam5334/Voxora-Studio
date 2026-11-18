"""Channel profile selection, preview, diagnostics and explicit project apply UI."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.universal.models import UniversalState
from app.universal.profiles import (
    evaluate_profile_rules,
    get_builtin_profile,
    list_builtin_profiles,
)


class ChannelProfileTab(ttk.Frame):
    """Project-local profile editor. Selection is a preview until Apply is confirmed."""

    def __init__(self, master, context) -> None:
        super().__init__(master, style="App.TFrame", padding=20)
        self.ctx = context
        self._profiles = {item.profile_id: item for item in list_builtin_profiles()}
        self._by_name = {item.display_name: key for key, item in self._profiles.items()}
        self._profile_var = tk.StringVar()
        self._preset_var = tk.StringVar()
        self._status_var = tk.StringVar(value="Choose a channel profile to preview its defaults.")
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        ttk.Label(self, text="Channel Profile", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            self,
            text="Profiles provide creative defaults and review guidance. Nothing is saved until you confirm Apply.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(0, 16))

        controls = ttk.Frame(self, style="App.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        controls.columnconfigure(1, weight=1)
        ttk.Label(controls, text="Channel", style="App.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self._profile_combo = ttk.Combobox(
            controls, textvariable=self._profile_var, state="readonly",
            values=[item.display_name for item in self._profiles.values()], style="App.TCombobox",
        )
        self._profile_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self._profile_combo.bind("<<ComboboxSelected>>", self._on_profile_changed)
        ttk.Label(controls, text="Production preset", style="App.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        self._preset_combo = ttk.Combobox(
            controls, textvariable=self._preset_var, state="readonly", style="App.TCombobox"
        )
        self._preset_combo.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
        self._preset_combo.bind("<<ComboboxSelected>>", lambda _event: self._render_preview())
        actions = ttk.Frame(controls, style="App.TFrame")
        actions.grid(row=0, column=2, rowspan=2, sticky="ns")
        ttk.Button(actions, text="Apply to Project", style="Primary.TButton", command=self._apply).pack(
            fill="x", pady=(0, 6)
        )
        ttk.Button(actions, text="Refresh", style="Secondary.TButton", command=self.refresh).pack(fill="x")

        preview = ttk.Frame(self, style="Card.TFrame", padding=14)
        preview.grid(row=3, column=0, sticky="nsew", pady=(0, 12))
        preview.columnconfigure(0, weight=1)
        ttk.Label(preview, text="Profile Preview", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self._description = ttk.Label(preview, text="", style="Muted.TLabel", wraplength=900, justify="left")
        self._description.grid(row=1, column=0, sticky="w", pady=(6, 10))
        self._defaults = ttk.Label(preview, text="", style="App.TLabel", wraplength=900, justify="left")
        self._defaults.grid(row=2, column=0, sticky="w")

        diagnostics = ttk.Frame(self, style="App.TFrame")
        diagnostics.grid(row=4, column=0, sticky="nsew")
        diagnostics.columnconfigure(0, weight=1)
        diagnostics.rowconfigure(1, weight=1)
        ttk.Label(diagnostics, text="Rule Diagnostics", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        self._diagnostics = tk.Text(
            diagnostics, height=8, wrap="word", state="disabled",
            background=self.ctx.palette["field_bg"], foreground=self.ctx.palette["fg"],
            insertbackground=self.ctx.palette["fg"], relief="flat", padx=9, pady=8,
            highlightthickness=1, highlightbackground=self.ctx.palette["border"],
        )
        self._diagnostics.grid(row=1, column=0, sticky="nsew")
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(10, 0)
        )

    def _selected_profile(self):
        return self._profiles.get(self._by_name.get(self._profile_var.get(), ""))

    def _on_profile_changed(self, _event=None) -> None:
        profile = self._selected_profile()
        presets = list(profile.presets) if profile else []
        self._preset_combo.configure(values=[item.display_name for item in presets])
        self._preset_var.set("")
        if presets:
            self._preset_combo.configure(state="readonly")
        else:
            self._preset_combo.configure(state="disabled")
        self._render_preview()

    def _selected_preset_id(self, profile):
        name = self._preset_var.get()
        return next((item.preset_id for item in profile.presets if item.display_name == name), None) if profile else None

    def _render_preview(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            self._description.configure(text="No built-in profile selected.")
            self._defaults.configure(text="")
            self._set_diagnostics(["Select a profile to inspect its rules."])
            return
        preset_id = self._selected_preset_id(profile)
        preset = next((item for item in profile.presets if item.preset_id == preset_id), None)
        visual = preset.visual_defaults if preset and preset.visual_defaults.style_family != "unspecified" else profile.visual_defaults
        tags = tuple(dict.fromkeys((*profile.visual_defaults.style_tags, *(preset.visual_defaults.style_tags if preset else ()))))
        mood = tuple(dict.fromkeys((*profile.visual_defaults.mood, *(preset.visual_defaults.mood if preset else ()))))
        guidance = tuple(dict.fromkeys((*profile.visual_defaults.composition_guidance, *(preset.visual_defaults.composition_guidance if preset else ()))))
        production = profile.production_defaults
        lines = [
            f"Visual style: {visual.style_family}",
            f"Style tags: {', '.join(tags) or 'Not specified'}",
            f"Mood: {', '.join(mood) or 'Not specified'}",
            f"Production: {production.aspect_ratio or 'Default aspect'} · {production.resolution or 'Default resolution'} · {production.frame_rate or 'Default FPS'} FPS",
        ]
        if guidance:
            lines.append("Composition guidance: " + " ".join(guidance))
        if profile.narration_defaults:
            lines.append("Narration defaults: " + ", ".join(f"{k}: {v}" for k, v in profile.narration_defaults.items()))
        self._description.configure(text=f"{profile.display_name} — {profile.description}")
        self._defaults.configure(text="\n".join(lines))
        project = self.ctx.project()
        state = UniversalState.from_project_settings(project.settings)
        diagnostics = evaluate_profile_rules(
            profile,
            project=project,
            scenes=project.scenes,
            scene_plans=list(state.scene_plans.values()),
            selected_preset_id=preset_id,
        )
        rendered = [
            f"[{item.severity.upper()}] {item.code}: {item.message}"
            for item in diagnostics
        ]
        if not rendered:
            rendered = ["No current rule diagnostics. Manual review rules may appear when a relevant scene plan is evaluated."]
        self._set_diagnostics(rendered)
        self._status_var.set("Preview only — project settings are unchanged.")

    def _set_diagnostics(self, lines) -> None:
        self._diagnostics.configure(state="normal")
        self._diagnostics.delete("1.0", "end")
        self._diagnostics.insert("1.0", "\n".join(lines))
        self._diagnostics.configure(state="disabled")

    def _apply(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            messagebox.showwarning("Channel Profile", "Select a channel profile first.", parent=self)
            return
        project = self.ctx.project()
        state = UniversalState.from_project_settings(project.settings)
        if state.read_only:
            messagebox.showerror(
                "Channel Profile",
                "This project's Universal settings use an unsupported or malformed format and are read-only.",
                parent=self,
            )
            return
        preset_id = self._selected_preset_id(profile)
        preset_name = self._preset_var.get() or "Profile defaults"
        if not messagebox.askyesno(
            "Apply Channel Profile",
            f"Apply {profile.display_name} ({preset_name}) to this project?\n\n"
            "This stores a project-local profile snapshot. Existing scenes, narration, prompts, "
            "assets and render settings will not be rewritten.",
            parent=self,
        ):
            return
        try:
            state.set_profile_snapshot(profile, selected_preset_id=preset_id)
            project.settings = state.apply_to_project_settings(project.settings)
            self.ctx.script.mark_project_dirty()
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Channel Profile", str(exc), parent=self)
            return
        self._status_var.set(f"Applied {profile.display_name} to this project. Save the project to keep the change.")
        self._render_preview()

    def refresh(self) -> None:
        project = self.ctx.project()
        state = UniversalState.from_project_settings(project.settings)
        snapshot = state.profile_snapshot
        if snapshot is not None and not snapshot.read_only:
            profile = self._profiles.get(snapshot.profile_id)
            if profile is not None:
                self._profile_var.set(profile.display_name)
                self._on_profile_changed()
                if snapshot.selected_preset_id:
                    preset = next((p for p in profile.presets if p.preset_id == snapshot.selected_preset_id), None)
                    self._preset_var.set(preset.display_name if preset else "")
                    self._render_preview()
                self._status_var.set(f"Saved project profile: {profile.display_name}")
                return
        self._profile_var.set("")
        self._preset_var.set("")
        self._preset_combo.configure(values=[], state="disabled")
        self._render_preview()
        if snapshot is not None and snapshot.read_only:
            self._status_var.set("Saved profile snapshot is from a newer format and is preserved read-only.")

    def apply_theme(self, palette: dict) -> None:
        self._diagnostics.configure(
            background=palette["field_bg"], foreground=palette["fg"], insertbackground=palette["fg"],
            highlightbackground=palette["border"],
        )
