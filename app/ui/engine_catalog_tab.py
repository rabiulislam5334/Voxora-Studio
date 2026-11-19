"""Read-only catalog of scene engines, composition renderers, and visual providers."""
from __future__ import annotations
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from app.audio.ffmpeg_tool import FFmpegTool
from app.core.settings_store import SettingsStore
from app.universal.builtins import build_builtin_engine_runtime_registry
from app.universal.composition_builtins import build_builtin_composition_render_bridge
from app.universal.adapters.raster import RasterCompositionAdapter
from app.universal.providers.stable_diffusion_cpp import StableDiffusionCppProvider
from app.universal.visual_generation_settings import LocalImageGenerationSettings, load_local_image_generation_settings


def format_capabilities(capabilities) -> str:
    groups = (("Scene kinds", capabilities.scene_kinds), ("Style tags", capabilities.style_tags),
              ("Asset kinds", capabilities.asset_kinds), ("Output formats", capabilities.output_formats))
    lines = [f"{label}: {', '.join(values) if values else 'Not declared'}" for label, values in groups]
    lines.extend((f"GPU required: {'Yes' if capabilities.requires_gpu else 'No'}",
                  f"Draft render: {'Supported' if capabilities.supports_draft_render else 'Not declared'}",
                  f"Maximum concurrent jobs: {capabilities.max_concurrent_jobs or 'Not declared'}",
                  f"Estimated memory: {str(capabilities.estimated_memory_mb) + ' MB' if capabilities.estimated_memory_mb else 'Not declared'}"))
    return "\n".join(lines)


def format_composition_capabilities(adapter) -> str:
    caps = adapter.composition_capabilities
    return "\n".join((f"Output formats: {', '.join(caps.output_formats)}",
                      f"Asset kinds: {', '.join(caps.asset_kinds)}",
                      f"Layer support: {'Yes' if caps.supports_layers else 'No'}",
                      f"Transform support: {'Yes' if caps.supports_transforms else 'No'}",
                      f"Opacity support: {'Yes' if caps.supports_opacity else 'No'}",
                      f"Rotation support: {'Yes' if caps.supports_rotation else 'No'}",
                      "Output type: Still image (one transparent PNG frame)",
                      "GPU required: No", "Video output: Not supported"))


def format_provider_capabilities(descriptor) -> str:
    caps = descriptor.capabilities
    memory = f"{caps.estimated_memory_mb} MB" if caps.estimated_memory_mb else "Not declared"
    return "\n".join((f"Model profiles: {', '.join(descriptor.model_ids) or 'Not declared'}",
                      f"Output formats: {', '.join(caps.output_formats)}",
                      f"Maximum dimensions: {caps.max_width} × {caps.max_height}",
                      f"Maximum images per request: {caps.max_images_per_request}",
                      f"Reference images: {'Supported' if caps.supports_reference_images else 'Not supported'}",
                      f"Seed: {'Supported' if caps.supports_seed else 'Not supported'}",
                      f"Network required: {'Yes' if caps.requires_network else 'No'}",
                      f"API key required: {'Yes' if caps.requires_api_key else 'No'}",
                      f"Estimated memory: {memory}"))


class EngineCatalogTab(ttk.Frame):
    CATEGORY_INFO = {
        "category:segments": ("Scene Segment Engines", "Render complete scene segments for the video production pipeline. These engines are not automatically composition renderers."),
        "category:compositions": ("Composition Renderers", "Render layered still compositions. The built-in raster renderer produces PNG only; it is not an MP4 engine."),
        "category:providers": ("Visual Generation Providers", "Generate source artwork for the Visual Asset Library. Provider availability is based on explicit local setup and does not trigger generation."),
    }

    def __init__(self, master, *, config, palette) -> None:
        super().__init__(master, style="App.TFrame", padding=20)
        self._palette, self._config = palette, config
        self._ffmpeg = FFmpegTool(SettingsStore(config.settings_file))
        self._entries = {}
        self._status_var = tk.StringVar(value="Catalog loaded without starting dependency checks.")
        self._build()
        self.refresh(probe_availability=False)

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text="Engine & Provider Catalog", style="PageTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(self, text="Inspect scene engines, still-composition renderers, and visual-generation providers separately. "
                  "Refreshing this catalog never selects, switches, downloads, or starts a provider.",
                  style="Muted.TLabel", wraplength=1000, justify="left").grid(row=1, column=0, sticky="w", pady=(0, 14))
        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(actions, text="Refresh Catalog", style="Secondary.TButton",
                   command=lambda: self.refresh(probe_availability=False)).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Check Segment Engine Availability", style="Primary.TButton",
                   command=lambda: self.refresh(probe_availability=True)).pack(side="left")
        body = ttk.Frame(self, style="App.TFrame")
        body.grid(row=3, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=2); body.rowconfigure(0, weight=1)
        listing = ttk.Frame(body, style="Card.TFrame", padding=10)
        listing.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        listing.columnconfigure(0, weight=1); listing.rowconfigure(1, weight=1)
        ttk.Label(listing, text="Registered Capabilities", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._tree = ttk.Treeview(listing, columns=("status", "version"), show="tree headings", selectmode="browse", height=12)
        self._tree.heading("#0", text="Capability"); self._tree.heading("status", text="Availability"); self._tree.heading("version", text="Version")
        self._tree.column("#0", width=270, anchor="w"); self._tree.column("status", width=115, anchor="center"); self._tree.column("version", width=100, anchor="w")
        self._tree.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(listing, orient="vertical", command=self._tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns"); self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        details = ttk.Frame(body, style="Card.TFrame", padding=12)
        details.grid(row=0, column=1, sticky="nsew"); details.columnconfigure(0, weight=1); details.rowconfigure(2, weight=1)
        ttk.Label(details, text="Capability Details", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        self._name = ttk.Label(details, text="Select a capability to inspect its metadata.", style="App.TLabel", wraplength=380)
        self._name.grid(row=1, column=0, sticky="w", pady=(8, 6))
        self._details = tk.Text(details, height=14, wrap="word", state="disabled",
            background=palette["field_bg"], foreground=palette["fg"], insertbackground=palette["fg"],
            relief="flat", padx=9, pady=8)
        self._details.grid(row=2, column=0, sticky="nsew")
        ttk.Label(self, text="Catalog entries are informational only. Production engine/provider choice remains explicit in its own workflow.",
                  style="Muted.TLabel", wraplength=1000, justify="left").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Label(self, textvariable=self._status_var, style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(6, 0))

    def _set_details(self, value):
        self._details.configure(state="normal"); self._details.delete("1.0", "end")
        self._details.insert("1.0", value); self._details.configure(state="disabled")

    def _on_select(self, _event=None):
        selection = self._tree.selection()
        if not selection: return
        selected_id = selection[0]
        if selected_id in self.CATEGORY_INFO:
            title, description = self.CATEGORY_INFO[selected_id]
            self._name.configure(text=title); self._set_details(description); return
        entry = self._entries.get(selected_id)
        if entry is None: return
        kind, descriptor, diagnostic = entry
        metadata = descriptor.descriptor if kind == "composition_renderer" else descriptor
        identity = metadata.provider_id if kind == "provider" else metadata.engine_id
        self._name.configure(text=f"{metadata.display_name}  ·  {identity}")
        lines = [f"Category: {kind.replace('_', ' ').title()}", f"Version: {metadata.version}",
                 f"Availability: {'Available' if metadata.available else 'Unavailable / not configured'}"]
        if diagnostic: lines.extend(("", f"Diagnostic: {diagnostic}"))
        if kind == "segment_engine": lines.extend(("", format_capabilities(descriptor.capabilities)))
        elif kind == "composition_renderer": lines.extend(("", format_composition_capabilities(descriptor)))
        else: lines.extend(("", format_provider_capabilities(descriptor)))
        self._set_details("\n".join(lines))

    def apply_theme(self, palette):
        self._palette = palette
        self._details.configure(background=palette["field_bg"], foreground=palette["fg"],
                                insertbackground=palette["fg"], highlightbackground=palette["border"])

    def refresh(self, *, probe_availability=False):
        try:
            registry = build_builtin_engine_runtime_registry(self._ffmpeg, probe_availability=probe_availability)
            segment_descriptors = registry.list_engines(include_unavailable=True)
            composition_bridge = build_builtin_composition_render_bridge()
            raster_adapter = RasterCompositionAdapter()
            composition_resolution = composition_bridge.inspect("raster")
            settings_path = Path(self._config.userdata_dir) / "visual_generation.json"
            try:
                settings = load_local_image_generation_settings(settings_path)
                provider_descriptor = StableDiffusionCppProvider(
                    settings.executable_path, settings.model_path, threads=settings.threads, steps=settings.steps
                ).descriptor
                provider_diagnostic = "" if provider_descriptor.available else "Configure a valid local sd-cli executable and model in Image Generation."
            except Exception as exc:
                defaults = LocalImageGenerationSettings()
                provider_descriptor = StableDiffusionCppProvider("", "", threads=defaults.threads, steps=defaults.steps).descriptor
                provider_diagnostic = f"Local provider settings are invalid: {exc}"
        except Exception as exc:
            self._status_var.set(f"Catalog refresh failed: {exc}"); return

        selected = self._tree.selection()
        selected_id = selected[0] if selected else None
        children = self._tree.get_children()
        if children: self._tree.delete(*children)
        self._entries = {}
        for category_id, (title, _description) in self.CATEGORY_INFO.items():
            self._tree.insert("", "end", iid=category_id, text=title, values=("", ""), open=True)
        for descriptor in segment_descriptors:
            item_id = f"segment:{descriptor.engine_id}"
            self._entries[item_id] = ("segment_engine", descriptor, descriptor.unavailable_reason)
            self._tree.insert("category:segments", "end", iid=item_id, text=descriptor.display_name,
                              values=("Available" if descriptor.available else "Unavailable", descriptor.version))
        self._entries["composition:raster"] = ("composition_renderer", raster_adapter,
            "" if composition_resolution.supported else composition_resolution.reason)
        self._tree.insert("category:compositions", "end", iid="composition:raster",
            text=raster_adapter.descriptor.display_name,
            values=("Available" if composition_resolution.supported else "Unavailable", raster_adapter.descriptor.version))
        self._entries["provider:stable-diffusion-cpp"] = ("provider", provider_descriptor, provider_diagnostic)
        self._tree.insert("category:providers", "end", iid="provider:stable-diffusion-cpp",
            text=provider_descriptor.display_name,
            values=("Available" if provider_descriptor.available else "Not configured", provider_descriptor.version))
        if selected_id in self._entries or selected_id in self.CATEGORY_INFO: self._tree.selection_set(selected_id)
        else: self._tree.selection_set("segment:ffmpeg" if "segment:ffmpeg" in self._entries else "category:segments")
        self._on_select()
        self._status_var.set("Segment engine availability checked. Local provider paths were inspected only; no provider was started."
            if probe_availability else "Catalog refreshed. No generation, downloads, or network checks were started.")
