"""Local visual asset and reusable character library workspace."""
from __future__ import annotations

import json
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.universal.asset_library import AssetImportError, VisualAssetLibrary
from app.universal.visual_assets import (
    AssetProvenance,
    CharacterAppearance,
    CharacterDefinition,
)


def format_asset_inspection(asset) -> str:
    """Return stable, display-ready asset facts without reading the image."""
    size = asset.metadata.get("file_size_bytes")
    size_text = f"{size:,} bytes" if isinstance(size, int) else "Unknown"
    dimensions = (
        f"{asset.width} × {asset.height}"
        if asset.width is not None and asset.height is not None else "Unknown"
    )
    provenance = asset.provenance
    lines = [
        f"Asset ID: {asset.asset_id}",
        f"Kind: {asset.kind}",
        f"Media type: {asset.media_type or 'Unknown'}",
        f"Dimensions: {dimensions}",
        f"File size: {size_text}",
        f"SHA-256: {asset.content_sha256 or 'Not recorded'}",
        f"Stored path: {asset.location}",
        f"Tags: {', '.join(asset.tags) if asset.tags else 'None'}",
        f"Source: {provenance.source if provenance else 'Not recorded'}",
        f"License declaration: {provenance.license if provenance and provenance.license else 'Not recorded'}",
        f"Attribution: {provenance.attribution if provenance and provenance.attribution else 'Not recorded'}",
        f"Source URI: {provenance.source_uri if provenance and provenance.source_uri else 'Not recorded'}",
    ]
    return "\n".join(lines)


def format_character_inspection(character) -> str:
    appearance = character.appearance
    return "\n".join((
        f"Character: {character.display_name}",
        f"Character ID: {character.character_id}",
        f"Appearance ID: {appearance.appearance_id}",
        f"Appearance fingerprint: {appearance.appearance_fingerprint}",
        f"Reference assets: {', '.join(appearance.reference_asset_ids) or 'None'}",
        f"Style tags: {', '.join(appearance.style_tags) or 'None'}",
    ))


class AssetLibraryTab(ttk.Frame):
    """Two-tab local catalog editor; never mutates Project/.voxora data."""

    def __init__(self, master, *, config, palette) -> None:
        super().__init__(master, style="App.TFrame", padding=18)
        self._palette = palette
        self.library = VisualAssetLibrary(Path(config.assets_dir) / "visual_library")
        self._assets = {}
        self._characters = {}
        self._selected_asset_id = None
        self._selected_character_id = None
        self._preview_image = None
        self._status = tk.StringVar(value="Local visual library ready.")
        self._build()
        self.refresh()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        ttk.Label(self, text="Visual Asset Library", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            self,
            text="Manage local images and reusable character appearances. "
                 "Imported files stay on this device; no AI or network service is used.",
            style="Muted.TLabel", wraplength=1000, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=2, column=0, sticky="nsew")
        self.assets_page = ttk.Frame(self.notebook, style="App.TFrame", padding=10)
        self.characters_page = ttk.Frame(self.notebook, style="App.TFrame", padding=10)
        self.notebook.add(self.assets_page, text="Assets")
        self.notebook.add(self.characters_page, text="Characters")
        self._build_assets_page()
        self._build_characters_page()
        ttk.Label(self, textvariable=self._status, style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", pady=(8, 0)
        )

    def _build_assets_page(self):
        page = self.assets_page
        page.columnconfigure(0, weight=3)
        page.columnconfigure(1, weight=4)
        page.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(page, style="App.TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Button(toolbar, text="Import Images", style="Primary.TButton",
                   command=self._import_images).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Refresh", style="Secondary.TButton",
                   command=self.refresh).pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=28)
        search.pack(side="right")
        search.bind("<KeyRelease>", lambda _event: self._populate_assets())
        ttk.Label(toolbar, text="Search", style="Muted.TLabel").pack(side="right", padx=(0, 6))

        listing = ttk.Frame(page, style="Card.TFrame", padding=8)
        listing.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.asset_tree = ttk.Treeview(
            listing, columns=("kind", "dimensions", "tags"),
            show="tree headings", selectmode="browse",
        )
        self.asset_tree.heading("#0", text="Asset")
        self.asset_tree.heading("kind", text="Kind")
        self.asset_tree.heading("dimensions", text="Size")
        self.asset_tree.heading("tags", text="Tags")
        self.asset_tree.column("#0", width=180, anchor="w")
        self.asset_tree.column("kind", width=90, anchor="w")
        self.asset_tree.column("dimensions", width=100, anchor="center")
        self.asset_tree.column("tags", width=150, anchor="w")
        self.asset_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.asset_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.asset_tree.configure(yscrollcommand=scroll.set)
        self.asset_tree.bind("<<TreeviewSelect>>", self._on_asset_select)

        details = ttk.Frame(page, style="Card.TFrame", padding=10)
        details.grid(row=1, column=1, sticky="nsew")
        details.columnconfigure(0, weight=1)
        details.rowconfigure(1, weight=1)
        ttk.Label(details, text="Image Preview & Inspection",
                  style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        split = ttk.Panedwindow(details, orient="vertical")
        split.grid(row=1, column=0, sticky="nsew", pady=(8, 8))
        preview_frame = ttk.Frame(split, style="App.TFrame", height=210)
        self.preview_label = ttk.Label(
            preview_frame, text="Select an image to preview", style="Muted.TLabel",
            anchor="center",
        )
        self.preview_label.pack(fill="both", expand=True)
        split.add(preview_frame, weight=1)
        info_frame = ttk.Frame(split, style="App.TFrame")
        self.asset_info = tk.Text(
            info_frame, height=9, wrap="word", state="disabled",
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            insertbackground=self._palette["fg"], relief="flat", padx=8, pady=6,
        )
        self.asset_info.pack(fill="both", expand=True)
        split.add(info_frame, weight=1)

        editor = ttk.LabelFrame(details, text="Editable Catalog Metadata", padding=8)
        editor.grid(row=2, column=0, sticky="ew")
        editor.columnconfigure(1, weight=1)
        self.asset_kind_var = tk.StringVar()
        self.asset_tags_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.license_var = tk.StringVar()
        self.attribution_var = tk.StringVar()
        self.source_uri_var = tk.StringVar()
        fields = (
            ("Kind", self.asset_kind_var), ("Tags (comma separated)", self.asset_tags_var),
            ("Source", self.source_var), ("License declaration", self.license_var),
            ("Attribution", self.attribution_var), ("Source URI", self.source_uri_var),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(editor, text=label, style="Muted.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=2
            )
            ttk.Entry(editor, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=2
            )
        actions = ttk.Frame(details, style="App.TFrame")
        actions.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Save Metadata", style="Primary.TButton",
                   command=self._save_asset_metadata).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Verify Integrity", style="Secondary.TButton",
                   command=self._verify_selected_asset).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Remove from Catalog", style="Secondary.TButton",
                   command=self._remove_selected_asset).pack(side="right")

    def _build_characters_page(self):
        page = self.characters_page
        page.columnconfigure(0, weight=1)
        page.columnconfigure(1, weight=2)
        page.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(page, style="App.TFrame")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Button(toolbar, text="New Character", style="Primary.TButton",
                   command=self._new_character).pack(side="left", padx=(0, 8))
        ttk.Button(toolbar, text="Refresh", style="Secondary.TButton",
                   command=self.refresh).pack(side="left")
        listing = ttk.Frame(page, style="Card.TFrame", padding=8)
        listing.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(0, weight=1)
        self.character_tree = ttk.Treeview(
            listing, columns=("id", "appearance"), show="tree headings",
            selectmode="browse",
        )
        self.character_tree.heading("#0", text="Character")
        self.character_tree.heading("id", text="Character ID")
        self.character_tree.heading("appearance", text="Appearance")
        self.character_tree.column("#0", width=150)
        self.character_tree.column("id", width=150)
        self.character_tree.column("appearance", width=150)
        self.character_tree.grid(row=0, column=0, sticky="nsew")
        self.character_tree.bind("<<TreeviewSelect>>", self._on_character_select)

        editor = ttk.Frame(page, style="Card.TFrame", padding=10)
        editor.grid(row=1, column=1, sticky="nsew")
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(3, weight=1)
        ttk.Label(editor, text="Character & Appearance Editor",
                  style="SectionTitle.TLabel").grid(row=0, column=0, columnspan=2,
                                                     sticky="w", pady=(0, 8))
        self.character_id_var = tk.StringVar()
        self.character_name_var = tk.StringVar()
        self.appearance_id_var = tk.StringVar()
        self.style_tags_var = tk.StringVar()
        for row, (label, variable) in enumerate((
            ("Character ID", self.character_id_var),
            ("Display name", self.character_name_var),
            ("Appearance ID", self.appearance_id_var),
            ("Style tags (comma separated)", self.style_tags_var),
        ), start=1):
            ttk.Label(editor, text=label, style="Muted.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 8), pady=3
            )
            ttk.Entry(editor, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=3
            )
        ttk.Label(editor, text="Description", style="Muted.TLabel").grid(
            row=5, column=0, sticky="nw", padx=(0, 8), pady=3
        )
        self.character_description = tk.Text(editor, height=3, wrap="word")
        self.character_description.grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="Visual appearance", style="Muted.TLabel").grid(
            row=6, column=0, sticky="nw", padx=(0, 8), pady=3
        )
        self.appearance_description = tk.Text(editor, height=5, wrap="word")
        self.appearance_description.grid(row=6, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="Attributes (JSON object)", style="Muted.TLabel").grid(
            row=7, column=0, sticky="nw", padx=(0, 8), pady=3
        )
        self.character_attributes = tk.Text(editor, height=4, wrap="word")
        self.character_attributes.grid(row=7, column=1, sticky="ew", pady=3)
        ttk.Label(editor, text="Reference assets (Ctrl/Shift select)", style="Muted.TLabel").grid(
            row=8, column=0, sticky="nw", padx=(0, 8), pady=3
        )
        refs_frame = ttk.Frame(editor, style="App.TFrame")
        refs_frame.grid(row=8, column=1, sticky="nsew")
        self.reference_list = tk.Listbox(
            refs_frame, selectmode="extended", height=5,
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            selectbackground=self._palette["accent"],
        )
        self.reference_list.pack(side="left", fill="both", expand=True)
        ref_scroll = ttk.Scrollbar(refs_frame, orient="vertical",
                                   command=self.reference_list.yview)
        ref_scroll.pack(side="right", fill="y")
        self.reference_list.configure(yscrollcommand=ref_scroll.set)
        ttk.Label(editor, text="Appearance Inspection", style="Muted.TLabel").grid(
            row=9, column=0, sticky="nw", padx=(0, 8), pady=3
        )
        self.character_inspection = tk.Text(
            editor, height=5, wrap="word", state="disabled",
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            relief="flat", padx=8, pady=6,
        )
        self.character_inspection.grid(row=9, column=1, sticky="ew", pady=3)
        actions = ttk.Frame(editor, style="App.TFrame")
        actions.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Save Character", style="Primary.TButton",
                   command=self._save_character).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Delete Character", style="Secondary.TButton",
                   command=self._remove_character).pack(side="right")

    def refresh(self):
        try:
            catalog = self.library.load_catalog()
        except AssetImportError as exc:
            self._status.set(f"Library error: {exc}")
            return
        self._assets = {item.asset_id: item for item in catalog.assets}
        self._characters = {item.character_id: item for item in catalog.characters}
        self._populate_assets()
        self._populate_characters()
        self._populate_reference_assets()
        self._status.set(
            f"{len(self._assets)} assets · {len(self._characters)} characters · "
            f"Library: {self.library.root}"
        )

    def _populate_assets(self):
        if not hasattr(self, "asset_tree"):
            return
        query = self.search_var.get().strip().casefold()
        for item in self.asset_tree.get_children():
            self.asset_tree.delete(item)
        for asset in sorted(self._assets.values(), key=lambda value: value.asset_id.casefold()):
            searchable = " ".join((
                asset.asset_id, asset.kind, asset.location, *asset.tags,
                asset.media_type or "",
            )).casefold()
            if query and query not in searchable:
                continue
            dimensions = f"{asset.width}×{asset.height}" if asset.width and asset.height else "—"
            self.asset_tree.insert(
                "", "end", iid=asset.asset_id, text=asset.asset_id,
                values=(asset.kind, dimensions, ", ".join(asset.tags)),
            )
        if self._selected_asset_id in self._assets:
            self.asset_tree.selection_set(self._selected_asset_id)

    def _populate_characters(self):
        for item in self.character_tree.get_children():
            self.character_tree.delete(item)
        for character in sorted(self._characters.values(),
                                key=lambda value: value.display_name.casefold()):
            self.character_tree.insert(
                "", "end", iid=character.character_id, text=character.display_name,
                values=(character.character_id, character.appearance.appearance_id),
            )
        if self._selected_character_id in self._characters:
            self.character_tree.selection_set(self._selected_character_id)

    def _populate_reference_assets(self, selected_ids=()):
        self.reference_list.delete(0, "end")
        self._reference_asset_ids = []
        for asset in sorted(self._assets.values(), key=lambda value: value.asset_id.casefold()):
            self._reference_asset_ids.append(asset.asset_id)
            self.reference_list.insert("end", f"{asset.asset_id}  ·  {asset.kind}")
            if asset.asset_id in selected_ids:
                index = len(self._reference_asset_ids) - 1
                self.reference_list.selection_set(index)

    def _import_images(self):
        paths = filedialog.askopenfilenames(
            parent=self, title="Import visual assets",
            filetypes=(("Supported images", "*.png *.jpg *.jpeg *.gif *.bmp"),
                       ("All files", "*.*")),
        )
        if not paths:
            return
        imported, failures = 0, []
        for path in paths:
            try:
                self.library.import_file(path)
                imported += 1
            except Exception as exc:
                failures.append(f"{Path(path).name}: {exc}")
        self.refresh()
        message = f"Imported {imported} image(s)."
        if failures:
            message += "\n\nCould not import:\n" + "\n".join(failures[:8])
        self._status.set(message)

    def _on_asset_select(self, _event=None):
        selection = self.asset_tree.selection()
        if not selection:
            return
        asset = self._assets.get(selection[0])
        if asset is None:
            return
        self._selected_asset_id = asset.asset_id
        self._set_text(self.asset_info, format_asset_inspection(asset))
        self.asset_kind_var.set(asset.kind)
        self.asset_tags_var.set(", ".join(asset.tags))
        provenance = asset.provenance
        self.source_var.set(provenance.source if provenance else "")
        self.license_var.set(provenance.license or "" if provenance else "")
        self.attribution_var.set(provenance.attribution or "" if provenance else "")
        self.source_uri_var.set(provenance.source_uri or "" if provenance else "")
        self._show_preview(asset)

    def _show_preview(self, asset):
        self._preview_image = None
        try:
            path = self.library.resolve_asset_path(asset)
            try:
                from PIL import Image, ImageTk  # optional enhancement only
                with Image.open(path) as source:
                    image = source.copy()
                image.thumbnail((640, 360))
                self._preview_image = ImageTk.PhotoImage(image)
            except ImportError:
                if (asset.width or 0) * (asset.height or 0) > 16_000_000:
                    raise ValueError("Pillow is not installed; native preview is limited to 16 megapixels.")
                self._preview_image = tk.PhotoImage(file=str(path))
                width, height = self._preview_image.width(), self._preview_image.height()
                factor = max(1, (width + 639) // 640, (height + 359) // 360)
                if factor > 1:
                    self._preview_image = self._preview_image.subsample(factor, factor)
            self.preview_label.configure(image=self._preview_image, text="")
        except Exception as exc:
            self.preview_label.configure(
                image="", text=f"Preview unavailable\n{exc}", anchor="center",
                justify="center",
            )

    def _save_asset_metadata(self):
        asset = self._assets.get(self._selected_asset_id)
        if asset is None:
            messagebox.showinfo("Select an asset", "Choose an asset before editing metadata.", parent=self)
            return
        try:
            tags = tuple(dict.fromkeys(
                value.strip() for value in self.asset_tags_var.get().split(",") if value.strip()
            ))
            source = self.source_var.get().strip()
            provenance = AssetProvenance(
                source=source or "user-supplied",
                license=self.license_var.get().strip() or None,
                attribution=self.attribution_var.get().strip() or None,
                source_uri=self.source_uri_var.get().strip() or None,
                metadata=asset.provenance.metadata if asset.provenance else {},
                extra=asset.provenance.extra if asset.provenance else {},
            )
            updated = replace(
                asset, kind=self.asset_kind_var.get().strip(), tags=tags,
                provenance=provenance,
            )
            self.library.update_asset(updated)
            self.refresh()
            self.asset_tree.selection_set(updated.asset_id)
            self._on_asset_select()
            self._status.set(f"Saved metadata for {updated.asset_id}.")
        except Exception as exc:
            messagebox.showerror("Metadata not saved", str(exc), parent=self)

    def _verify_selected_asset(self):
        asset = self._assets.get(self._selected_asset_id)
        if asset is None:
            return
        try:
            valid = self.library.verify_asset(asset)
            self._status.set(
                f"Integrity verified: {asset.asset_id}" if valid
                else f"Integrity check failed: content hash mismatch for {asset.asset_id}"
            )
        except Exception as exc:
            self._status.set(f"Integrity check failed: {exc}")

    def _remove_selected_asset(self):
        asset = self._assets.get(self._selected_asset_id)
        if asset is None:
            return
        if not messagebox.askyesno(
            "Remove asset from catalog",
            "Remove this entry from the catalog? The stored image file will be retained on disk.",
            parent=self,
        ):
            return
        try:
            self.library.remove_asset(asset.asset_id)
            self._selected_asset_id = None
            self.refresh()
            self._set_text(self.asset_info, "")
            self.preview_label.configure(image="", text="Select an image to preview")
            self._preview_image = None
        except Exception as exc:
            messagebox.showerror("Asset not removed", str(exc), parent=self)

    def _new_character(self):
        self._selected_character_id = None
        self.character_id_var.set("")
        self.character_name_var.set("")
        self.appearance_id_var.set("")
        self.style_tags_var.set("")
        for widget in (self.character_description, self.appearance_description):
            widget.delete("1.0", "end")
        self.character_attributes.delete("1.0", "end")
        self.character_attributes.insert("1.0", "{}")
        self._populate_reference_assets()
        self._set_text(self.character_inspection, "")

    def _on_character_select(self, _event=None):
        selection = self.character_tree.selection()
        if not selection:
            return
        character = self._characters.get(selection[0])
        if character is None:
            return
        self._selected_character_id = character.character_id
        appearance = character.appearance
        self.character_id_var.set(character.character_id)
        self.character_name_var.set(character.display_name)
        self.appearance_id_var.set(appearance.appearance_id)
        self.style_tags_var.set(", ".join(appearance.style_tags))
        self.character_description.delete("1.0", "end")
        self.character_description.insert("1.0", character.description)
        self.appearance_description.delete("1.0", "end")
        self.appearance_description.insert("1.0", appearance.visual_description)
        self.character_attributes.delete("1.0", "end")
        self.character_attributes.insert(
            "1.0", json.dumps(dict(appearance.attributes), ensure_ascii=False, indent=2)
        )
        self._populate_reference_assets(appearance.reference_asset_ids)
        self._set_text(self.character_inspection, format_character_inspection(character))

    def _save_character(self):
        try:
            character_id = self.character_id_var.get().strip()
            if self._selected_character_id and character_id != self._selected_character_id:
                raise ValueError("Character IDs are stable and cannot be changed after creation.")
            name = self.character_name_var.get().strip()
            appearance_id = self.appearance_id_var.get().strip() or f"{character_id}-appearance-v1"
            description = self.character_description.get("1.0", "end-1c")
            visual_description = self.appearance_description.get("1.0", "end-1c").strip()
            attributes = json.loads(self.character_attributes.get("1.0", "end-1c") or "{}")
            if not isinstance(attributes, dict):
                raise ValueError("Attributes must be a JSON object.")
            selected = self.reference_list.curselection()
            reference_ids = tuple(self._reference_asset_ids[index] for index in selected)
            styles = tuple(dict.fromkeys(
                value.strip() for value in self.style_tags_var.get().split(",") if value.strip()
            ))
            existing = self._characters.get(character_id)
            existing_appearance = existing.appearance if existing else None
            character = CharacterDefinition(
                character_id=character_id,
                display_name=name,
                description=description,
                appearance=CharacterAppearance(
                    appearance_id=appearance_id,
                    visual_description=visual_description,
                    reference_asset_ids=reference_ids,
                    style_tags=styles,
                    attributes=attributes,
                    extra=existing_appearance.extra if existing_appearance else {},
                ),
                metadata=existing.metadata if existing else {},
                extra=existing.extra if existing else {},
            )
            self.library.save_character(character)
            self._selected_character_id = character_id
            self.refresh()
            self.character_tree.selection_set(character_id)
            self._on_character_select()
            self._status.set(f"Saved character {name} ({character_id}).")
        except Exception as exc:
            messagebox.showerror("Character not saved", str(exc), parent=self)

    def _remove_character(self):
        character = self._characters.get(self._selected_character_id)
        if character is None:
            return
        if not messagebox.askyesno(
            "Delete character",
            f"Remove '{character.display_name}' from the local character catalog?",
            parent=self,
        ):
            return
        try:
            self.library.remove_character(character.character_id)
            self._selected_character_id = None
            self.refresh()
            self._new_character()
        except Exception as exc:
            messagebox.showerror("Character not removed", str(exc), parent=self)

    @staticmethod
    def _set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def apply_theme(self, palette):
        self._palette = palette
        self.asset_info.configure(
            background=palette["field_bg"], foreground=palette["fg"],
            insertbackground=palette["fg"],
        )
        self.reference_list.configure(
            background=palette["field_bg"], foreground=palette["fg"],
            selectbackground=palette["accent"],
        )
        self.character_inspection.configure(
            background=palette["field_bg"], foreground=palette["fg"],
        )
