"""Read-only catalog of registered production engines."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.audio.ffmpeg_tool import FFmpegTool
from app.core.settings_store import SettingsStore
from app.universal.builtins import build_builtin_engine_runtime_registry


def format_capabilities(capabilities) -> str:
    """Format declared engine capabilities without probing or initializing engines."""
    groups = (
        ("Scene kinds", capabilities.scene_kinds),
        ("Style tags", capabilities.style_tags),
        ("Asset kinds", capabilities.asset_kinds),
        ("Output formats", capabilities.output_formats),
    )
    lines = [
        f"{label}: {', '.join(values) if values else 'Not declared'}"
        for label, values in groups
    ]
    lines.extend((
        f"GPU required: {'Yes' if capabilities.requires_gpu else 'No'}",
        f"Draft render: {'Supported' if capabilities.supports_draft_render else 'Not declared'}",
        f"Maximum concurrent jobs: {capabilities.max_concurrent_jobs or 'Not declared'}",
        f"Estimated memory: {str(capabilities.estimated_memory_mb) + ' MB' if capabilities.estimated_memory_mb else 'Not declared'}",
    ))
    return "\n".join(lines)


class EngineCatalogTab(ttk.Frame):
    """Read-only engine catalog; availability probing is an explicit user action."""

    def __init__(self, master, *, config, palette) -> None:
        super().__init__(master, style="App.TFrame", padding=20)
        self._palette = palette
        self._ffmpeg = FFmpegTool(SettingsStore(config.settings_file))
        self._descriptors = {}
        self._status_var = tk.StringVar(value="Catalog loaded without starting dependency checks.")
        self._build()
        self.refresh(probe_availability=False)

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text="Engine Catalog", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            self,
            text="Inspect registered engines, availability, capabilities and diagnostics. "
                 "This catalog never selects or switches an engine.",
            style="Muted.TLabel", wraplength=900, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 14))

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(
            actions, text="Refresh Catalog", style="Secondary.TButton",
            command=lambda: self.refresh(probe_availability=False),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions, text="Check Availability", style="Primary.TButton",
            command=lambda: self.refresh(probe_availability=True),
        ).pack(side="left")

        body = ttk.Frame(self, style="App.TFrame")
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        listing = ttk.Frame(body, style="Card.TFrame", padding=10)
        listing.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        listing.columnconfigure(0, weight=1)
        listing.rowconfigure(1, weight=1)
        ttk.Label(listing, text="Registered Engines", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        self._tree = ttk.Treeview(
            listing, columns=("status", "version"), show="tree headings",
            selectmode="browse", height=12,
        )
        self._tree.heading("#0", text="Engine")
        self._tree.heading("status", text="Availability")
        self._tree.heading("version", text="Version")
        self._tree.column("#0", width=220, anchor="w")
        self._tree.column("status", width=115, anchor="center")
        self._tree.column("version", width=130, anchor="w")
        self._tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self._tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        details = ttk.Frame(body, style="Card.TFrame", padding=12)
        details.grid(row=0, column=1, sticky="nsew")
        details.columnconfigure(0, weight=1)
        details.rowconfigure(2, weight=1)
        ttk.Label(details, text="Engine Details", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self._name = ttk.Label(details, text="Select an engine to inspect its metadata.",
                               style="App.TLabel", wraplength=380)
        self._name.grid(row=1, column=0, sticky="w", pady=(8, 6))
        self._details = tk.Text(
            details, height=14, wrap="word", state="disabled",
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            insertbackground=self._palette["fg"], relief="flat", padx=9, pady=8,
            highlightthickness=1, highlightbackground=self._palette["border"],
        )
        self._details.grid(row=2, column=0, sticky="nsew")

        ttk.Label(
            self,
            text="Compatible alternatives are informational only. Changing an engine requires a separate explicit choice.",
            style="Muted.TLabel", wraplength=900, justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(6, 0)
        )

    def _set_details(self, value: str) -> None:
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        self._details.insert("1.0", value)
        self._details.configure(state="disabled")

    def _on_select(self, _event=None) -> None:
        selection = self._tree.selection()
        if not selection:
            return
        descriptor = self._descriptors.get(selection[0])
        if descriptor is None:
            return
        self._name.configure(text=f"{descriptor.display_name}  ·  {descriptor.engine_id}")
        lines = [
            f"Version: {descriptor.version}",
            f"Availability: {'Available' if descriptor.available else 'Unavailable'}",
        ]
        if descriptor.unavailable_reason:
            lines.append(f"Diagnostic: {descriptor.unavailable_reason}")
        lines.extend(("", format_capabilities(descriptor.capabilities)))
        self._set_details("\n".join(lines))

    def apply_theme(self, palette) -> None:
        self._palette = palette
        self._details.configure(
            background=palette["field_bg"], foreground=palette["fg"],
            insertbackground=palette["fg"], highlightbackground=palette["border"],
        )

    def refresh(self, *, probe_availability: bool = False) -> None:
        try:
            registry = build_builtin_engine_runtime_registry(
                self._ffmpeg, probe_availability=probe_availability
            )
            descriptors = registry.list_engines(include_unavailable=True)
        except Exception as exc:
            self._status_var.set(f"Catalog refresh failed: {exc}")
            return

        selected = self._tree.selection()
        selected_id = selected[0] if selected else None
        children = self._tree.get_children()
        if children:
            self._tree.delete(*children)
        self._descriptors = {item.engine_id: item for item in descriptors}
        for descriptor in descriptors:
            self._tree.insert(
                "", "end", iid=descriptor.engine_id, text=descriptor.display_name,
                values=("Available" if descriptor.available else "Unavailable", descriptor.version),
            )
        if selected_id in self._descriptors:
            self._tree.selection_set(selected_id)
            self._on_select()
        elif descriptors:
            self._tree.selection_set(descriptors[0].engine_id)
            self._on_select()
        else:
            self._name.configure(text="No built-in engines are registered.")
            self._set_details("The engine registry is currently empty.")

        if probe_availability:
            self._status_var.set("Availability check completed. No engine was selected or initialized.")
        else:
            self._status_var.set("Catalog refreshed. Dependency checks were not started.")
