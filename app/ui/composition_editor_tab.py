"""Desktop editor for scene-level visual compositions.

The editor manipulates renderer-independent composition data. Applying a
composition persists it through the explicit, stale-safe Universal Core API;
it does not render a video or modify legacy Scene records.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app.projects.manager import ProjectManager
from app.universal.asset_library import VisualAssetLibrary
from app.universal.composition import (
    CompositionCanvas,
    CompositionElement,
    SceneComposition,
    VisualTransform,
)
from app.universal.composition_workflow import (
    apply_scene_composition,
    preview_scene_composition,
)
from app.universal.models import UniversalState
from app.universal.generated_image_composition import append_bound_generated_images


def canvas_rect(transform: VisualTransform, width: int, height: int):
    """Map normalized composition geometry to integer canvas coordinates."""
    return (
        round(transform.x * width),
        round(transform.y * height),
        round((transform.x + transform.width) * width),
        round((transform.y + transform.height) * height),
    )


def move_transform(transform: VisualTransform, dx: float, dy: float) -> VisualTransform:
    """Move a normalized rectangle while keeping it inside the composition canvas."""
    x = min(max(0.0, transform.x + dx), 1.0 - transform.width)
    y = min(max(0.0, transform.y + dy), 1.0 - transform.height)
    return VisualTransform(
        x=x, y=y, width=transform.width, height=transform.height,
        anchor_x=transform.anchor_x, anchor_y=transform.anchor_y,
        rotation_degrees=transform.rotation_degrees, opacity=transform.opacity,
    )


class CompositionEditorTab(ttk.Frame):
    """A lightweight local drag-and-drop composition editor."""

    def __init__(
        self, master, *, config, palette, project_manager=None,
        on_open_project=None, on_save_project=None, on_project_dirty=None,
    ) -> None:
        super().__init__(master, style="App.TFrame", padding=16)
        self.config = config
        self.palette = palette
        self.project_manager = project_manager or ProjectManager()
        self._on_open_project_callback = on_open_project
        self._on_save_project_callback = on_save_project
        self._on_project_dirty_callback = on_project_dirty or (lambda: None)
        self.library = VisualAssetLibrary(Path(config.assets_dir) / "visual_library")
        self.catalog = None
        self.composition = None
        self.preview = None
        self._assets = {}
        self._photo_refs = []
        self._canvas_items = {}
        self._selected_element_id = None
        self._composition_dirty = False
        self._active_scene_id = None
        self._scene_ids = []
        self._drag_origin = None
        self._drag_transform = None
        self._canvas_origin = (0, 0)
        self._canvas_size = (960, 540)
        self._status = tk.StringVar(value="Open a .voxora project to edit a scene composition.")
        self._build()
        self._load_catalog()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="Scene Composition Editor", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            self,
            text="Arrange assets already bound to a scene. Drag to move; use the layer controls to reorder. "
                 "Preview is local and non-destructive until you explicitly apply it.",
            style="Muted.TLabel", wraplength=1100,
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))

        toolbar = ttk.Frame(self, style="App.TFrame")
        toolbar.grid(row=2, column=0, sticky="new", pady=(0, 8))
        for column in range(5):
            toolbar.columnconfigure(column, weight=0)
        ttk.Button(toolbar, text="Open Project…", style="Primary.TButton",
                   command=self._open_project).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(toolbar, text="Save Project", style="Secondary.TButton",
                   command=self._save_project).grid(row=0, column=1, padx=6)
        ttk.Button(toolbar, text="Refresh Library", style="Secondary.TButton",
                   command=self._load_catalog).grid(row=0, column=2, padx=6)
        ttk.Label(toolbar, text="Scene", style="Muted.TLabel").grid(row=0, column=3, padx=(12, 4))
        self.scene_var = tk.StringVar()
        self.scene_combo = ttk.Combobox(toolbar, textvariable=self.scene_var, state="readonly", width=28)
        self.scene_combo.grid(row=0, column=4, padx=4)
        self.scene_combo.bind("<<ComboboxSelected>>", self._load_scene)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew")
        self.rowconfigure(3, weight=1)
        left = ttk.Frame(body, style="App.TFrame", padding=(0, 0, 8, 0))
        center = ttk.Frame(body, style="App.TFrame", padding=6)
        right = ttk.Frame(body, style="App.TFrame", padding=(8, 0, 0, 0))
        body.add(left, weight=1)
        body.add(center, weight=4)
        body.add(right, weight=1)

        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="Bound Assets", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6))
        self.asset_var = tk.StringVar()
        self.asset_combo = ttk.Combobox(left, textvariable=self.asset_var, state="readonly", width=24)
        self.asset_combo.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(left, text="Add to Canvas", style="Primary.TButton",
                   command=self._add_asset).grid(row=2, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(left, text="Add Bound Generated Images",
                   style="Secondary.TButton",
                   command=self._add_bound_generated_images).grid(
                       row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(left, text="Layers (top first)", style="SectionTitle.TLabel").grid(
            row=3, column=0, sticky="w", pady=(4, 6))
        self.layer_tree = ttk.Treeview(left, columns=("asset",), show="tree headings", height=14,
                                       selectmode="browse")
        self.layer_tree.heading("#0", text="Element")
        self.layer_tree.heading("asset", text="Asset ID")
        self.layer_tree.column("#0", width=140)
        self.layer_tree.column("asset", width=120)
        self.layer_tree.grid(row=4, column=0, sticky="nsew")
        left.rowconfigure(4, weight=1)
        self.layer_tree.bind("<<TreeviewSelect>>", self._on_layer_select)
        layer_actions = ttk.Frame(left, style="App.TFrame")
        layer_actions.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(layer_actions, text="Remove", command=self._remove_element).pack(side="left", padx=(0, 4))
        ttk.Button(layer_actions, text="Up", command=lambda: self._reorder(1)).pack(side="left", padx=2)
        ttk.Button(layer_actions, text="Down", command=lambda: self._reorder(-1)).pack(side="left", padx=2)

        center.columnconfigure(0, weight=1)
        center.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(center, background="#252a33", highlightthickness=1,
                                highlightbackground="#555d6b", width=960, height=540)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._redraw)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        self.canvas.bind("<Double-Button-1>", self._reset_selected_transform)
        self.canvas.bind("<MouseWheel>", self._zoom_selected)

        right.columnconfigure(0, weight=1)
        ttk.Label(right, text="Selected Element", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8))
        self.property_text = tk.Text(right, width=28, height=13, wrap="word", state="disabled",
                                     background=self.palette["field_bg"], foreground=self.palette["fg"],
                                     insertbackground=self.palette["fg"], relief="flat")
        self.property_text.grid(row=1, column=0, sticky="nsew")
        ttk.Label(right, text="Double-click canvas to reset position/size. "
                  "Mouse wheel changes selected element size.", style="Muted.TLabel",
                  wraplength=230).grid(row=2, column=0, sticky="w", pady=(8, 0))
        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        ttk.Button(actions, text="Preview & Validate", style="Primary.TButton",
                   command=self._preview).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Apply Composition…", style="Secondary.TButton",
                   command=self._apply).pack(side="left", padx=6)
        ttk.Button(actions, text="Check Render Support", style="Secondary.TButton",
                   command=self._check_render_support).pack(side="left", padx=6)
        ttk.Label(self, textvariable=self._status, style="Muted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(4, 0))


    def _save_project(self):
        if self._on_save_project_callback is not None:
            self._on_save_project_callback()
            return
        from tkinter import filedialog
        try:
            if self.project_manager.current_path is None:
                save_path = filedialog.asksaveasfilename(
                    parent=self, title="Save Voxora project",
                    defaultextension=".voxora",
                    filetypes=(("Voxora projects", "*.voxora"),),
                )
                if not save_path:
                    return
                path = self.project_manager.save(Path(save_path))
            else:
                path = self.project_manager.save()
            self._status.set(f"Project saved: {path}")
        except Exception as exc:
            messagebox.showerror("Project not saved", str(exc), parent=self)

    def _check_render_support(self):
        from app.universal.composition_render_bridge import CompositionRenderBridge
        resolution = CompositionRenderBridge().inspect("ffmpeg")
        self._status.set("Composition render unavailable: " + resolution.reason)
        messagebox.showinfo(
            "Composition render capability",
            "The current FFmpeg segment adapter does not declare layered composition support. "
            "Voxora will not flatten layers or silently drop transforms. A renderer with an explicit "
            "render_composition() contract is required before composition export can be enabled.",
            parent=self,
        )

    def _load_catalog(self):
        try:
            self.catalog = self.library.load_catalog()
            self._assets = {asset.asset_id: asset for asset in self.catalog.assets}
            self._status.set(f"Visual library loaded: {len(self._assets)} assets.")
        except Exception as exc:
            self._status.set(f"Visual library unavailable: {exc}")

    def _open_project(self):
        if self._on_open_project_callback is not None:
            self._on_open_project_callback()
            return
        from tkinter import filedialog
        if self._composition_dirty and not messagebox.askyesno(
            "Discard composition edits",
            "The current composition has unapplied editor changes. Discard them and open another project?",
            parent=self,
        ):
            return
        if self.project_manager.dirty:
            choice = messagebox.askyesnocancel(
                "Unsaved composition changes",
                "Save the current project before opening another one?\n\n"
                "Yes = Save, No = Discard changes, Cancel = Stay here.",
                parent=self,
            )
            if choice is None:
                return
            if choice:
                try:
                    if self.project_manager.current_path is None:
                        save_path = filedialog.asksaveasfilename(
                            parent=self, title="Save Voxora project",
                            defaultextension=".voxora",
                            filetypes=(("Voxora projects", "*.voxora"),),
                        )
                        if not save_path:
                            return
                        self.project_manager.save(Path(save_path))
                    else:
                        self.project_manager.save()
                except Exception as exc:
                    messagebox.showerror("Project not saved", str(exc), parent=self)
                    return
        path = filedialog.askopenfilename(
            parent=self, title="Open Voxora project",
            initialdir=str(self.config.projects_dir),
            filetypes=(("Voxora projects", "*.voxora"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            self.project_manager.open(Path(path))
            project = self.project_manager.current_project
            self.scene_combo["values"] = [
                f"{scene.title}  [{scene.id}]" for scene in sorted(project.scenes, key=lambda item: item.order)
            ]
            self._scene_ids = [
                scene.id for scene in sorted(project.scenes, key=lambda item: item.order)
            ]
            self.scene_var.set("")
            self.composition = None
            self.preview = None
            self._composition_dirty = False
            self._active_scene_id = None
            self._clear_canvas()
            self._status.set(f"Opened {Path(path).name}. Choose a scene.")
        except Exception as exc:
            messagebox.showerror("Project not opened", str(exc), parent=self)

    def confirm_project_switch(self) -> bool:
        """Prevent Script workspace from replacing a project with a local draft."""
        if not self._composition_dirty:
            return True
        if not messagebox.askyesno(
            "Discard composition edits",
            "The current composition has unapplied editor changes. Discard them before switching projects?",
            parent=self,
        ):
            return False
        return True

    def refresh_project(self):
        """Reload the scene selector after the shared project is replaced."""
        project = self.project_manager.current_project
        ordered = sorted(project.scenes, key=lambda item: item.order)
        self._scene_ids = [scene.id for scene in ordered]
        self.scene_combo["values"] = [
            f"{scene.title}  [{scene.id}]" for scene in ordered
        ]
        self.scene_var.set("")
        self.composition = None
        self.preview = None
        self._composition_dirty = False
        self._active_scene_id = None
        self._selected_element_id = None
        self.asset_combo["values"] = ()
        self.asset_var.set("")
        self._populate_layers()
        self._redraw()
        suffix = self.project_manager.current_path.name if self.project_manager.current_path else "Unsaved project"
        self._status.set(f"Active project: {project.name} · {suffix}. Choose a scene.")

    def _load_scene(self, _event=None):
        if self.project_manager.current_project is None:
            return
        index = self.scene_combo.current()
        if index < 0 or index >= len(self._scene_ids):
            return
        scene_id = self._scene_ids[index]
        if (
            self._composition_dirty
            and self._active_scene_id is not None
            and scene_id != self._active_scene_id
        ):
            if not messagebox.askyesno(
                "Discard composition edits",
                "Discard unapplied edits to the current scene composition?",
                parent=self,
            ):
                previous = self._scene_ids.index(self._active_scene_id)
                self.scene_combo.current(previous)
                return
            self._composition_dirty = False
        self.composition = None
        self.preview = None
        self._selected_element_id = None
        self._clear_canvas()
        project = self.project_manager.current_project
        state = UniversalState.from_project_settings(project.settings)
        if state.read_only:
            messagebox.showerror("Universal data unavailable",
                                 "This project has future or malformed Universal data and cannot be edited safely.",
                                 parent=self)
            return
        plan = state.scene_plans.get(scene_id)
        if plan is None:
            messagebox.showinfo("No scene plan", "Bind at least one asset to this scene in Scene Assets first.",
                                parent=self)
            return
        bound = {item.asset_id for item in plan.asset_refs}
        options = sorted(bound)
        self.asset_combo["values"] = options
        self.asset_var.set(options[0] if options else "")
        stored_compositions = state.extra.get("scene_compositions", {})
        if not isinstance(stored_compositions, dict):
            messagebox.showerror("Composition unavailable", "Stored scene compositions data is malformed.", parent=self)
            return
        raw = stored_compositions.get(scene_id)
        if raw is not None:
            if not isinstance(raw, dict) or not isinstance(raw.get("composition"), dict):
                messagebox.showerror("Composition unavailable", "Stored composition entry is malformed.", parent=self)
                return
            try:
                self.composition = SceneComposition.from_dict(raw["composition"])
            except Exception as exc:
                messagebox.showerror("Composition unavailable", str(exc), parent=self)
                return
        else:
            self.composition = SceneComposition(
                composition_id=f"composition-{scene_id}",
                scene_id=scene_id,
                canvas=CompositionCanvas(1920, 1080),
                elements=(),
            )
        self.preview = None
        self._selected_element_id = None
        self._composition_dirty = False
        self._active_scene_id = scene_id
        self._populate_layers()
        self._redraw()
        self._status.set(f"Loaded composition for scene {scene_id}. Add bound assets to begin.")

    def _add_asset(self):
        if self.composition is None:
            messagebox.showinfo("Select a scene", "Open a project and select a scene first.", parent=self)
            return
        asset_id = self.asset_var.get().strip()
        if not asset_id:
            messagebox.showinfo("Select a bound asset", "Choose an asset already bound to this scene.", parent=self)
            return
        elements = list(self.composition.elements)
        index = len(elements)
        element_id = f"element-{index + 1:04d}"
        existing = {item.element_id for item in elements}
        while element_id in existing:
            index += 1
            element_id = f"element-{index + 1:04d}"
        offset = min(0.04 * len(elements), 0.4)
        elements.append(CompositionElement(
            element_id=element_id, asset_id=asset_id,
            transform=VisualTransform(x=offset, y=offset, width=0.5, height=0.5),
            layer_order=max((item.layer_order for item in elements), default=-1) + 1,
            label=asset_id,
        ))
        self.composition = self._with_elements(elements)
        self.preview = None
        self._composition_dirty = True
        self._populate_layers(select=element_id)
        self._redraw()
        self._status.set(f"Added {asset_id}. Drag it on the canvas to position.")

    def _add_bound_generated_images(self):
        """Add verified generated images already bound to the active scene."""
        if self.composition is None or self.project_manager.current_project is None:
            messagebox.showinfo(
                "Select a scene",
                "Open a project and select a scene before adding generated images.",
                parent=self,
            )
            return
        if self.catalog is None:
            messagebox.showinfo(
                "Visual library unavailable",
                "Refresh the Visual Asset Library, then try again.",
                parent=self,
            )
            return
        try:
            updated = append_bound_generated_images(
                self.project_manager.current_project, self.catalog, self.composition,
            )
            added = len(updated.elements) - len(self.composition.elements)
            self.composition = updated
            self.preview = None
            self._composition_dirty = True
            self._populate_layers(select=updated.elements[-1].element_id)
            self._redraw()
            self._status.set(
                f"Added {added} bound generated image(s) in an auto-grid. "
                "Review the layout, then Preview & Validate."
            )
        except Exception as exc:
            messagebox.showinfo("Generated images not added", str(exc), parent=self)

    def _with_elements(self, elements):
        return SceneComposition(
            composition_id=self.composition.composition_id,
            scene_id=self.composition.scene_id,
            canvas=self.composition.canvas,
            elements=tuple(elements),
            composition_version=self.composition.composition_version,
            metadata=self.composition.metadata,
            extra=self.composition.extra,
        )

    def _selected(self):
        return next((item for item in self.composition.elements
                     if item.element_id == self._selected_element_id), None) if self.composition else None

    def _populate_layers(self, select=None):
        for row in self.layer_tree.get_children():
            self.layer_tree.delete(row)
        if self.composition is None:
            return
        for item in sorted(self.composition.elements, key=lambda value: (value.layer_order, value.element_id), reverse=True):
            self.layer_tree.insert("", "end", iid=item.element_id,
                                   text=item.label or item.element_id, values=(item.asset_id,))
        target = select or self._selected_element_id
        if target and self.layer_tree.exists(target):
            self.layer_tree.selection_set(target)
            self.layer_tree.see(target)
            self._selected_element_id = target
        self._update_properties()

    def _on_layer_select(self, _event=None):
        selection = self.layer_tree.selection()
        self._selected_element_id = selection[0] if selection else None
        self.preview = None
        self._update_properties()
        self._redraw()

    def _update_properties(self):
        item = self._selected()
        if item is None:
            value = "No element selected."
        else:
            t = item.transform
            value = (
                f"Element: {item.element_id}\nAsset: {item.asset_id}\n"
                f"Layer: {item.layer_order}\nPosition: {t.x:.3f}, {t.y:.3f}\n"
                f"Size: {t.width:.3f} × {t.height:.3f}\n"
                f"Rotation: {t.rotation_degrees:.1f}°\nOpacity: {t.opacity:.2f}\n"
                f"Fit: {item.fit_mode}\nVisible: {item.visible}"
            )
        self.property_text.configure(state="normal")
        self.property_text.delete("1.0", "end")
        self.property_text.insert("1.0", value)
        self.property_text.configure(state="disabled")

    def _canvas_geometry(self):
        cw = max(1, self.canvas.winfo_width())
        ch = max(1, self.canvas.winfo_height())
        scale = min((cw - 24) / self.composition.canvas.width,
                    (ch - 24) / self.composition.canvas.height)
        width = max(1, round(self.composition.canvas.width * scale))
        height = max(1, round(self.composition.canvas.height * scale))
        return (cw - width) // 2, (ch - height) // 2, width, height

    def _clear_canvas(self):
        self.canvas.delete("all")
        self._canvas_items.clear()
        self._photo_refs.clear()

    def _redraw(self, _event=None):
        self._clear_canvas()
        if self.composition is None:
            self.canvas.create_text(20, 20, anchor="nw", fill="white",
                                    text="Open a project and choose a scene.")
            return
        ox, oy, width, height = self._canvas_geometry()
        self._canvas_origin = (ox, oy)
        self._canvas_size = (width, height)
        self.canvas.create_rectangle(ox, oy, ox + width, oy + height,
                                     fill="#111820", outline="#7d8795", width=1)
        for item in sorted(self.composition.elements, key=lambda value: (value.layer_order, value.element_id)):
            if not item.visible:
                continue
            t = item.transform
            x1, y1 = ox + round(t.x * width), oy + round(t.y * height)
            x2, y2 = ox + round((t.x + t.width) * width), oy + round((t.y + t.height) * height)
            image = self._load_preview_image(item.asset_id, max(1, x2-x1), max(1, y2-y1),
                                             item.fit_mode, t.opacity, t.rotation_degrees)
            if image is not None:
                image_id = self.canvas.create_image((x1+x2)//2, (y1+y2)//2, anchor="center", image=image)
                self._photo_refs.append(image)
            else:
                image_id = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#435268", outline="#d2d9e3")
                self.canvas.create_text((x1+x2)//2, (y1+y2)//2, fill="white",
                                        text=item.label or item.asset_id, width=max(40, x2-x1-12))
            self._canvas_items[item.element_id] = (image_id, (x1, y1, x2, y2))
            if item.element_id == self._selected_element_id:
                self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ffcf5a", width=2, dash=(4, 2))
                self.canvas.create_rectangle(x2-7, y2-7, x2+7, y2+7,
                                              fill="#ffcf5a", outline="#222222", tags=("resize-handle",))
        self.canvas.create_text(ox + 6, oy + 6, anchor="nw", fill="#dce4ef",
                                text=f"{self.composition.canvas.width} × {self.composition.canvas.height}")

    def _load_preview_image(self, asset_id, width, height, fit_mode="contain", opacity=1.0, rotation=0.0):
        asset = self._assets.get(asset_id)
        if asset is None:
            return None
        if (asset.width or 0) * (asset.height or 0) > 16_000_000:
            return None
        try:
            path = self.library.resolve_asset_path(asset)
            from PIL import Image, ImageOps, ImageTk
            target = (max(1, min(width, 800)), max(1, min(height, 600)))
            with Image.open(path) as source:
                source = source.convert("RGBA")
                if fit_mode == "cover":
                    image = ImageOps.fit(source, target, method=Image.Resampling.LANCZOS)
                elif fit_mode == "stretch":
                    image = source.resize(target, Image.Resampling.LANCZOS)
                else:
                    contained = ImageOps.contain(source, target, method=Image.Resampling.LANCZOS)
                    image = Image.new("RGBA", target, (0, 0, 0, 0))
                    image.alpha_composite(contained, (
                        (target[0] - contained.width) // 2,
                        (target[1] - contained.height) // 2,
                    ))
                if rotation:
                    image = image.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=False)
                if opacity < 1.0:
                    alpha = image.getchannel("A").point(lambda value: round(value * opacity))
                    image.putalpha(alpha)
                return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _hit_test(self, x, y):
        for item in sorted(self.composition.elements, key=lambda value: (value.layer_order, value.element_id), reverse=True):
            geometry = self._canvas_items.get(item.element_id)
            if geometry is None:
                continue
            x1, y1, x2, y2 = geometry[1]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return item
        return None

    def _drag_start(self, event):
        if self.composition is None:
            return
        selected = self._selected()
        if selected is not None:
            geom = self._canvas_items.get(selected.element_id)
            if geom and abs(event.x - geom[1][2]) <= 10 and abs(event.y - geom[1][3]) <= 10:
                self._drag_origin = (event.x, event.y)
                self._drag_transform = selected.transform
                self._drag_mode = "resize"
                return
        hit = self._hit_test(event.x, event.y)
        if hit is None:
            self._selected_element_id = None
            self._populate_layers()
            self._redraw()
            return
        self._selected_element_id = hit.element_id
        self._drag_origin = (event.x, event.y)
        self._drag_transform = hit.transform
        self._drag_mode = "move"
        self._populate_layers(select=hit.element_id)
        self._redraw()

    def _drag_motion(self, event):
        if self.composition is None or self._drag_origin is None or self._drag_transform is None:
            return
        _, _, width, height = self._canvas_geometry()
        dx = (event.x - self._drag_origin[0]) / max(1, width)
        dy = (event.y - self._drag_origin[1]) / max(1, height)
        elements = []
        for item in self.composition.elements:
            if item.element_id != self._selected_element_id:
                elements.append(item)
                continue
            if self._drag_mode == "resize":
                new_width = min(1.0 - item.transform.x, max(0.03, self._drag_transform.width + dx))
                new_height = min(1.0 - item.transform.y, max(0.03, self._drag_transform.height + dy))
                transform = VisualTransform(
                    x=item.transform.x, y=item.transform.y, width=new_width, height=new_height,
                    anchor_x=item.transform.anchor_x, anchor_y=item.transform.anchor_y,
                    rotation_degrees=item.transform.rotation_degrees, opacity=item.transform.opacity,
                )
            else:
                transform = move_transform(self._drag_transform, dx, dy)
            elements.append(CompositionElement(
                element_id=item.element_id, asset_id=item.asset_id, transform=transform,
                layer_order=item.layer_order, fit_mode=item.fit_mode, visible=item.visible,
                label=item.label, metadata=item.metadata, extra=item.extra,
            ))
        self.composition = self._with_elements(elements)
        self.preview = None
        self._composition_dirty = True
        self._redraw()
        self._update_properties()

    def _drag_end(self, _event=None):
        self._drag_origin = None
        self._drag_transform = None

    def _reset_selected_transform(self, _event=None):
        item = self._selected()
        if item is None:
            return
        elements = []
        for value in self.composition.elements:
            if value.element_id == item.element_id:
                transform = VisualTransform()
                elements.append(CompositionElement(
                    element_id=value.element_id, asset_id=value.asset_id, transform=transform,
                    layer_order=value.layer_order, fit_mode=value.fit_mode, visible=value.visible,
                    label=value.label, metadata=value.metadata, extra=value.extra,
                ))
            else:
                elements.append(value)
        self.composition = self._with_elements(elements)
        self.preview = None
        self._composition_dirty = True
        self._redraw()
        self._update_properties()

    def _zoom_selected(self, event):
        item = self._selected()
        if item is None:
            return
        factor = 1.05 if event.delta > 0 else 0.95
        width = min(1.0 - item.transform.x, max(0.03, item.transform.width * factor))
        height = min(1.0 - item.transform.y, max(0.03, item.transform.height * factor))
        elements = []
        for value in self.composition.elements:
            if value.element_id == item.element_id:
                t = value.transform
                transform = VisualTransform(
                    x=t.x, y=t.y, width=width, height=height,
                    anchor_x=t.anchor_x, anchor_y=t.anchor_y,
                    rotation_degrees=t.rotation_degrees, opacity=t.opacity,
                )
                elements.append(CompositionElement(
                    element_id=value.element_id, asset_id=value.asset_id, transform=transform,
                    layer_order=value.layer_order, fit_mode=value.fit_mode, visible=value.visible,
                    label=value.label, metadata=value.metadata, extra=value.extra,
                ))
            else:
                elements.append(value)
        self.composition = self._with_elements(elements)
        self.preview = None
        self._composition_dirty = True
        self._redraw()
        self._update_properties()

    def _remove_element(self):
        item = self._selected()
        if item is None:
            return
        elements = [value for value in self.composition.elements if value.element_id != item.element_id]
        self.composition = self._with_elements(elements)
        self._selected_element_id = None
        self.preview = None
        self._composition_dirty = True
        self._populate_layers()
        self._redraw()

    def _reorder(self, delta):
        item = self._selected()
        if item is None:
            return
        elements = list(self.composition.elements)
        ordered = sorted(elements, key=lambda value: (value.layer_order, value.element_id))
        index = next(i for i, value in enumerate(ordered) if value.element_id == item.element_id)
        other_index = index + delta
        if not 0 <= other_index < len(ordered):
            return
        ordered[index], ordered[other_index] = ordered[other_index], ordered[index]
        replacements = {value.element_id: position for position, value in enumerate(ordered)}
        self.composition = self._with_elements([
            CompositionElement(
                element_id=value.element_id, asset_id=value.asset_id, transform=value.transform,
                layer_order=replacements[value.element_id], fit_mode=value.fit_mode,
                visible=value.visible, label=value.label, metadata=value.metadata, extra=value.extra,
            ) for value in elements
        ])
        self.preview = None
        self._composition_dirty = True
        self._populate_layers(select=item.element_id)
        self._redraw()

    def _preview(self):
        if self.project_manager.current_project is None or self.composition is None:
            messagebox.showinfo("Select a scene", "Open a project and select a scene first.", parent=self)
            return
        try:
            self.preview = preview_scene_composition(self.project_manager.current_project, self.composition)
            errors = sum(item.severity == "error" for item in self.preview.diagnostics)
            warnings = sum(item.severity == "warning" for item in self.preview.diagnostics)
            self._status.set(f"Composition preview: {len(self.preview.elements)} elements, {errors} errors, {warnings} warnings.")
            if errors:
                messagebox.showerror("Composition validation", "\n".join(
                    f"{item.code}: {item.message}" for item in self.preview.diagnostics
                    if item.severity == "error"), parent=self)
            else:
                messagebox.showinfo("Composition preview", "Layout validated. Review warnings before applying.\n\n" +
                    "\n".join(f"{item.severity.upper()}: {item.message}" for item in self.preview.diagnostics),
                    parent=self)
        except Exception as exc:
            messagebox.showerror("Preview failed", str(exc), parent=self)

    def _apply(self):
        if self.preview is None:
            messagebox.showinfo("Preview required", "Run Preview & Validate and review the result first.", parent=self)
            return
        if not self.preview.is_valid:
            messagebox.showwarning("Cannot apply", "Resolve blocking validation errors first.", parent=self)
            return
        if not messagebox.askyesno(
            "Apply composition",
            "Persist this reviewed composition to the project?\n\n"
            "This does not render a video. The project will be marked unsaved.",
            parent=self,
        ):
            return
        try:
            apply_scene_composition(self.project_manager.current_project,
                                    self.composition, self.preview, approved=True)
            self.project_manager.mark_dirty()
            self._on_project_dirty_callback()
            self.preview = None
            self._composition_dirty = False
            self._status.set("Composition applied in memory. Use Save Project to persist the .voxora file.")
        except Exception as exc:
            messagebox.showerror("Composition not applied", str(exc), parent=self)

    def _clear_canvas(self):
        self._clear()
        self.layer_tree.delete(*self.layer_tree.get_children())

    def _clear(self):
        self.canvas.delete("all")
        self._photo_refs.clear()
        self._canvas_items.clear()

    def apply_theme(self, palette):
        self.palette = palette
        self.property_text.configure(background=palette["field_bg"], foreground=palette["fg"],
                                      insertbackground=palette["fg"])
