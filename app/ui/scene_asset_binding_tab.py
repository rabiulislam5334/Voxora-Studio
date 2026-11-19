"""Scene-level visual asset and character binding workspace."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.projects.manager import ProjectManager
from app.universal.asset_library import VisualAssetLibrary
from app.universal.models import UniversalState
from app.universal.scene_asset_bindings import (
    SceneAssetBinding, apply_scene_bindings, preview_scene_bindings,
)
from app.universal.generated_image_scene_workflow import (
    preview_generated_image_binding, apply_generated_image_binding,
)
from app.universal.asset_continuity import analyze_asset_continuity


def format_binding_preview(preview) -> str:
    lines = [
        f"Scene: {preview.scene_id}",
        f"Assets to bind: {len(preview.asset_bindings)}",
        f"Characters to bind: {len(preview.character_bindings)}",
        f"Preview fingerprint: {preview.target_fingerprint}",
        "",
    ]
    if preview.diagnostics:
        lines.append("Diagnostics:")
        lines.extend(f"[{item.severity.upper()}] {item.code}: {item.message}"
                     for item in preview.diagnostics)
    else:
        lines.append("No binding conflicts detected. Review the selection before applying.")
    return "\n".join(lines)


def format_continuity_report(report) -> str:
    lines = [
        f"Continuity diagnostics: {len(report.diagnostics)}",
        f"Asset reuse groups: {len(report.asset_reuse_groups)}",
        f"Character groups: {len(report.character_groups)}",
    ]
    for item in report.diagnostics:
        scenes = ", ".join(item.scene_ids) or "Project"
        lines.append(f"[{item.severity.upper()}] {item.code} — {scenes}: {item.message}")
    for item in report.asset_reuse_groups:
        lines.append(f"REUSE {item.identity}: assets={', '.join(item.asset_ids)}; scenes={', '.join(item.scene_ids)}")
    for item in report.character_groups:
        lines.append(f"CHARACTER {item.character_id}: scenes={', '.join(item.scene_ids)}; "
                     f"appearances={len(item.appearance_fingerprints)}")
    return "\n".join(lines)


class SceneAssetBindingTab(ttk.Frame):
    """Explicit project/scene binding UI backed by the reviewed domain APIs."""

    def __init__(
        self, master, *, config, palette, project_manager=None,
        on_open_project=None, on_save_project=None, on_project_dirty=None,
    ) -> None:
        super().__init__(master, style="App.TFrame", padding=18)
        self.app_config = config
        self.palette = palette
        self.project_manager = project_manager or ProjectManager()
        self._on_open_project_callback = on_open_project
        self._on_save_project_callback = on_save_project
        self._on_project_dirty_callback = on_project_dirty or (lambda: None)
        self.library = VisualAssetLibrary(Path(config.assets_dir) / "visual_library")
        self.catalog = None
        self._preview = None
        self._preview_generated_only = False
        self._preview_image = None
        self._asset_ids = []
        self._character_ids = []
        self._status = tk.StringVar(value="Open a .voxora project to manage scene bindings.")
        self._build()
        self._load_catalog()

    def _build(self):
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Scene Assets & Continuity", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(self, text="Bind library images and reusable characters to a scene. "
                  "Changes are explicit and remain unsaved until you save the project.",
                  style="Muted.TLabel", wraplength=1100).grid(
            row=1, column=0, sticky="w", pady=(0, 12))
        toolbar = ttk.Frame(self, style="App.TFrame")
        toolbar.grid(row=2, column=0, sticky="new", pady=(0, 10))
        ttk.Button(toolbar, text="Open Project…", style="Primary.TButton",
                   command=self._open_project).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Save Project", style="Secondary.TButton",
                   command=self._save_project).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Refresh Library", style="Secondary.TButton",
                   command=self._load_catalog).pack(side="left")
        self.project_label = ttk.Label(toolbar, text="No project open", style="Muted.TLabel")
        self.project_label.pack(side="right")

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)
        left = ttk.Frame(body, style="App.TFrame", padding=(0, 0, 8, 0))
        right = ttk.Frame(body, style="App.TFrame", padding=(8, 0, 0, 0))
        body.add(left, weight=1)
        body.add(right, weight=3)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Project Scenes", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        self.scene_tree = ttk.Treeview(left, columns=("id",), show="tree headings", selectmode="browse")
        self.scene_tree.heading("#0", text="Scene")
        self.scene_tree.heading("id", text="Scene ID")
        self.scene_tree.column("#0", width=170)
        self.scene_tree.column("id", width=130)
        self.scene_tree.grid(row=1, column=0, sticky="nsew")
        self.scene_tree.bind("<<TreeviewSelect>>", self._on_scene_select)

        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text="Select Assets", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(right, text="Select Characters", style="SectionTitle.TLabel").grid(
            row=0, column=1, sticky="w", pady=(0, 6))
        asset_box = ttk.Frame(right, style="Card.TFrame", padding=8)
        asset_box.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        asset_box.columnconfigure(0, weight=1)
        asset_box.rowconfigure(0, weight=1)
        self.asset_list = tk.Listbox(asset_box, selectmode="extended", exportselection=False,
            background=self.palette["field_bg"], foreground=self.palette["fg"],
            selectbackground=self.palette["accent"])
        self.asset_list.grid(row=0, column=0, sticky="nsew")
        self.asset_list.bind("<<ListboxSelect>>", self._on_asset_select)
        self.asset_preview = ttk.Label(asset_box, text="Select an asset to preview",
            style="Muted.TLabel", anchor="center")
        self.asset_preview.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.role_var = tk.StringVar(value="visual")
        ttk.Label(asset_box, text="Role for selected assets", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(asset_box, textvariable=self.role_var).grid(row=3, column=0, sticky="ew")

        char_box = ttk.Frame(right, style="Card.TFrame", padding=8)
        char_box.grid(row=1, column=1, sticky="nsew", padx=(6, 0))
        char_box.columnconfigure(0, weight=1)
        char_box.rowconfigure(0, weight=1)
        self.character_list = tk.Listbox(char_box, selectmode="extended", exportselection=False,
            background=self.palette["field_bg"], foreground=self.palette["fg"],
            selectbackground=self.palette["accent"])
        self.character_list.grid(row=0, column=0, sticky="nsew")
        self.character_list.bind("<<ListboxSelect>>", self._invalidate_preview)
        self.role_var.trace_add("write", self._invalidate_preview)

        actions = ttk.Frame(right, style="App.TFrame")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 8))
        ttk.Button(actions, text="Preview Bindings", style="Primary.TButton",
                   command=self._preview_bindings).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Preview Generated Images", style="Secondary.TButton",
                   command=self._preview_generated_bindings).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Apply Reviewed Bindings", style="Secondary.TButton",
                   command=self._apply_bindings).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Analyze Continuity", style="Secondary.TButton",
                   command=self._analyze_continuity).pack(side="left")

        self.report = tk.Text(right, height=10, wrap="word", state="disabled",
            background=self.palette["field_bg"], foreground=self.palette["fg"],
            insertbackground=self.palette["fg"], relief="flat", padx=8, pady=6)
        self.report.grid(row=3, column=0, columnspan=2, sticky="nsew")
        right.rowconfigure(3, weight=1)
        ttk.Label(self, textvariable=self._status, style="Muted.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0))

    def _load_catalog(self):
        try:
            self.catalog = self.library.load_catalog()
            self._asset_ids = []
            self.asset_list.delete(0, "end")
            for asset in self.catalog.assets:
                self._asset_ids.append(asset.asset_id)
                self.asset_list.insert("end", f"{asset.asset_id}  ·  {asset.kind}  ·  "
                    f"{asset.width or '?'}×{asset.height or '?'}")
            self._character_ids = []
            self.character_list.delete(0, "end")
            for character in self.catalog.characters:
                self._character_ids.append(character.character_id)
                self.character_list.insert("end", f"{character.display_name}  ·  {character.character_id}")
            self._status.set(f"Library loaded: {len(self._asset_ids)} assets, "
                             f"{len(self._character_ids)} characters.")
        except Exception as exc:
            self._status.set(f"Library unavailable: {exc}")

    def _open_project(self):
        if self._on_open_project_callback is not None:
            self._on_open_project_callback()
            return
        if self.project_manager.dirty:
            choice = messagebox.askyesnocancel(
                "Unsaved project changes",
                "Save the current project before opening another one?\n\n"
                "Yes = Save, No = Discard changes, Cancel = Stay here.",
                parent=self,
            )
            if choice is None:
                return
            if choice:
                try:
                    self.project_manager.save()
                except Exception as exc:
                    messagebox.showerror("Project not saved", str(exc), parent=self)
                    return
        path = filedialog.askopenfilename(parent=self, title="Open Voxora project",
            initialdir=str(self.app_config.projects_dir),
            filetypes=(("Voxora projects", "*.voxora"), ("All files", "*.*")))
        if not path:
            return
        try:
            self.project_manager.open(Path(path))
            self._preview = None
            self._preview_generated_only = False
            self._populate_scenes()
            self.project_label.configure(text=f"{self.project_manager.current_project.name} · {Path(path).name}")
            self._status.set(f"Opened {Path(path).name} ({len(self.project_manager.current_project.scenes)} scenes).")
        except Exception as exc:
            messagebox.showerror("Project not opened", str(exc), parent=self)

    def _save_project(self):
        if self._on_save_project_callback is not None:
            self._on_save_project_callback()
            return
        if self.project_manager.current_path is None:
            messagebox.showinfo("No project path", "Open a saved .voxora project before saving bindings.", parent=self)
            return
        try:
            path = self.project_manager.save()
            self._status.set(f"Project saved: {path}")
        except Exception as exc:
            messagebox.showerror("Project not saved", str(exc), parent=self)

    def refresh_project(self):
        """Refresh this workspace after the shared application project changes."""
        self._preview = None
        self._preview_generated_only = False
        self._preview_image = None
        self._populate_scenes()
        project = self.project_manager.current_project
        path = self.project_manager.current_path
        suffix = Path(path).name if path else "Unsaved project"
        self.project_label.configure(text=f"{project.name} · {suffix}")
        self._status.set(f"Active project: {project.name}. Select a scene to manage bindings.")

    def _populate_scenes(self):
        for item in self.scene_tree.get_children():
            self.scene_tree.delete(item)
        project = self.project_manager.current_project
        for scene in sorted(project.scenes, key=lambda item: item.order):
            self.scene_tree.insert("", "end", iid=scene.id, text=scene.title, values=(scene.id,))
        self._set_report("Select a scene, then choose assets and characters to bind.")

    def _on_scene_select(self, _event=None):
        self._preview = None
        scene_id = self._selected_scene_id()
        if scene_id is None:
            return
        project = self.project_manager.current_project
        scene = project.get_scene(scene_id)
        state = UniversalState.from_project_settings(project.settings)
        plan = state.scene_plans.get(scene_id) if not state.read_only else None
        lines = [f"Scene: {scene.title}", f"Scene ID: {scene.id}",
                 f"Narration: {scene.text[:500] or '(empty)'}"]
        if plan:
            lines.append("Already bound assets: " + (", ".join(x.asset_id for x in plan.asset_refs) or "None"))
            raw = plan.requirements.get("character_bindings", [])
            lines.append("Already bound characters: " + (", ".join(
                x.get("character_id", "?") for x in raw if isinstance(x, dict)) if isinstance(raw, list) else "Invalid"))
        self._set_report("\n".join(lines))

    def _selected_scene_id(self):
        selected = self.scene_tree.selection()
        return selected[0] if selected else None

    def _invalidate_preview(self, *_args):
        if self._preview is not None:
            self._preview = None
            self._preview_generated_only = False
            self._set_report("Selection changed. Create a new binding preview before applying.")

    def _on_asset_select(self, _event=None):
        self._invalidate_preview()
        self._preview_image = None
        selected = self.asset_list.curselection()
        if not selected or self.catalog is None:
            return
        asset = self.catalog.assets[selected[0]]
        try:
            path = self.library.resolve_asset_path(asset)
            try:
                from PIL import Image, ImageTk
                with Image.open(path) as source:
                    if source.width * source.height > 16_000_000:
                        raise ValueError("Preview limited to 16 megapixels.")
                    source.thumbnail((360, 200))
                    self._preview_image = ImageTk.PhotoImage(source.copy())
            except ImportError:
                if (asset.width or 0) * (asset.height or 0) > 16_000_000:
                    raise ValueError("Install Pillow for previewing this large image.")
                self._preview_image = tk.PhotoImage(file=str(path))
                factor = max(1, (self._preview_image.width() + 359) // 360,
                             (self._preview_image.height() + 199) // 200)
                if factor > 1:
                    self._preview_image = self._preview_image.subsample(factor, factor)
            self.asset_preview.configure(image=self._preview_image, text="")
        except Exception as exc:
            self.asset_preview.configure(image="", text=f"Preview unavailable: {exc}")

    def _preview_bindings(self):
        self._preview_generated_only = False
        project = self.project_manager.current_project
        scene_id = self._selected_scene_id()
        if scene_id is None or self.catalog is None:
            messagebox.showinfo("Select a project and scene", "Open or create a project in the Script workspace, then select a scene.", parent=self)
            return
        try:
            role = self.role_var.get().strip() or "visual"
            assets = tuple(SceneAssetBinding(self._asset_ids[index], role)
                           for index in self.asset_list.curselection())
            characters = tuple(self._character_ids[index]
                               for index in self.character_list.curselection())
            self._preview = preview_scene_bindings(project, self.catalog, scene_id,
                asset_bindings=assets, character_ids=characters)
            self._set_report(format_binding_preview(self._preview))
            self._status.set("Binding preview created. Applying requires a separate confirmation.")
        except Exception as exc:
            self._preview = None
            messagebox.showerror("Preview failed", str(exc), parent=self)

    def _preview_generated_bindings(self):
        project = self.project_manager.current_project
        scene_id = self._selected_scene_id()
        selected = self.asset_list.curselection()
        if scene_id is None or self.catalog is None:
            messagebox.showinfo("Select a project and scene", "Open or create a project in the Script workspace, then select a scene.", parent=self)
            return
        if self.character_list.curselection():
            messagebox.showinfo("Generated images only", "Clear character selections before previewing generated images.", parent=self)
            return
        try:
            asset_ids = tuple(self._asset_ids[index] for index in selected)
            self._preview = preview_generated_image_binding(
                project, self.catalog, scene_id, asset_ids,
                role=self.role_var.get().strip() or "visual",
            )
            self._preview_generated_only = True
            self._set_report(format_binding_preview(self._preview))
            self._status.set("Generated-image binding preview created. Review it before applying.")
        except Exception as exc:
            self._preview = None
            self._preview_generated_only = False
            messagebox.showerror("Generated-image preview failed", str(exc), parent=self)

    def _apply_bindings(self):
        if self._preview is None:
            messagebox.showinfo("Preview required", "Create and review a binding preview first.", parent=self)
            return
        if not self._preview.is_valid:
            messagebox.showwarning("Cannot apply", "Resolve preview errors before applying.", parent=self)
            return
        if not messagebox.askyesno("Apply scene bindings",
            "Apply these asset and character bindings to the selected scene?\n\n"
            "The project will be marked unsaved. Use Save Project to persist the changes.",
            parent=self):
            return
        try:
            if self._preview_generated_only:
                apply_generated_image_binding(
                    self.project_manager.current_project, self.catalog,
                    self._preview, approved=True,
                )
            else:
                apply_scene_bindings(
                    self.project_manager.current_project, self.catalog,
                    self._preview, approved=True,
                )
            self.project_manager.mark_dirty()
            self._on_project_dirty_callback()
            self._preview = None
            self._preview_generated_only = False
            self._on_scene_select()
            self._status.set("Bindings applied in memory. Save Project to persist them.")
        except Exception as exc:
            messagebox.showerror("Bindings not applied", str(exc), parent=self)

    def _analyze_continuity(self):
        if self.catalog is None:
            messagebox.showinfo("Open a project", "Open or create a project in the Script workspace first.", parent=self)
            return
        try:
            report = analyze_asset_continuity(self.project_manager.current_project, self.catalog)
            self._set_report(format_continuity_report(report))
            self._status.set("Continuity analysis completed (read-only).")
        except Exception as exc:
            messagebox.showerror("Analysis failed", str(exc), parent=self)

    def _set_report(self, value):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", value)
        self.report.configure(state="disabled")

    def apply_theme(self, palette):
        self.palette = palette
        for widget in (self.asset_list, self.character_list, self.report):
            widget.configure(background=palette["field_bg"], foreground=palette["fg"])
        self.asset_list.configure(selectbackground=palette["accent"])
        self.character_list.configure(selectbackground=palette["accent"])
        self.report.configure(insertbackground=palette["fg"])
