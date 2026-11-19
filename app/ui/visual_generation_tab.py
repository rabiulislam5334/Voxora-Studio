"""Desktop workflow for explicitly configured local image generation."""
from __future__ import annotations

import asyncio
import threading
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, ttk

from app.universal.asset_library import VisualAssetLibrary
from app.universal.providers.stable_diffusion_cpp import StableDiffusionCppProvider
from app.universal.visual_generation import VisualGenerationRequest
from app.universal.visual_generation_runtime import (
    VisualGenerationProgress,
    VisualGenerationRuntime,
)
from app.universal.visual_generation_settings import (
    LocalImageGenerationSettings,
    VisualGenerationSettingsError,
    load_local_image_generation_settings,
    save_local_image_generation_settings,
)


class VisualGenerationTab(ttk.Frame):
    """Local-only image generation page; all model work runs off the Tk thread."""

    def __init__(self, master, *, config, palette, async_bridge, on_open_assets):
        super().__init__(master, style="App.TFrame", padding=18)
        self._config = config
        self._palette = palette
        self._bridge = async_bridge
        self._on_open_assets = on_open_assets
        self._settings_path = Path(config.userdata_dir) / "visual_generation.json"
        self._library = VisualAssetLibrary(Path(config.assets_dir) / "visual_library")
        self._cancel_event = None
        self._running = False
        self._runtime = None
        self._provider = None
        self._status = tk.StringVar(value="Configure a local stable-diffusion.cpp executable and model.")
        self._executable_var = tk.StringVar()
        self._model_var = tk.StringVar()
        self._threads_var = tk.StringVar(value="4")
        self._steps_var = tk.StringVar(value="20")
        self._width_var = tk.StringVar(value="512")
        self._height_var = tk.StringVar(value="512")
        self._seed_var = tk.StringVar()
        self._build()
        self._load_settings()
        self.refresh_provider_status()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, text="Local Image Generation", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            self,
            text="Offline generation through Stable Diffusion.cpp. Voxora does not download models "
                 "or contact an online provider. A compatible local model and sd-cli executable are required.",
            style="Muted.TLabel", wraplength=980, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        setup = ttk.LabelFrame(self, text="Local Runtime Setup", padding=10)
        setup.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        setup.columnconfigure(1, weight=1)
        ttk.Label(setup, text="sd-cli executable").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(setup, textvariable=self._executable_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(setup, text="Browse", command=self._browse_executable).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(setup, text="Model file").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(setup, textvariable=self._model_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(setup, text="Browse", command=self._browse_model).grid(row=1, column=2, padx=(8, 0))
        ttk.Label(setup, text="CPU threads").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Spinbox(setup, from_=1, to=32, textvariable=self._threads_var, width=8).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(setup, text="Steps").grid(row=2, column=2, sticky="e", padx=(12, 4))
        ttk.Spinbox(setup, from_=1, to=100, textvariable=self._steps_var, width=8).grid(row=2, column=3, sticky="w", pady=4)
        actions = ttk.Frame(setup, style="App.TFrame")
        actions.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Save Setup", style="Primary.TButton", command=self.save_settings).pack(side="left")
        ttk.Button(actions, text="Check Setup", style="Secondary.TButton", command=self.refresh_provider_status).pack(side="left", padx=8)
        self._provider_status = ttk.Label(actions, text="Not configured", style="Muted.TLabel")
        self._provider_status.pack(side="left", padx=12)

        prompt_frame = ttk.LabelFrame(self, text="Image Prompt", padding=10)
        prompt_frame.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        prompt_frame.columnconfigure(0, weight=1)
        self._prompt = tk.Text(
            prompt_frame, height=5, wrap="word",
            background=palette["field_bg"], foreground=palette["fg"],
            insertbackground=palette["fg"], relief="flat", padx=8, pady=6,
        )
        self._prompt.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Label(prompt_frame, text="Negative prompt").grid(row=1, column=0, sticky="w", pady=(8, 2))
        self._negative = tk.Text(
            prompt_frame, height=2, wrap="word",
            background=palette["field_bg"], foreground=palette["fg"],
            insertbackground=palette["fg"], relief="flat", padx=8, pady=6,
        )
        self._negative.grid(row=2, column=0, columnspan=4, sticky="ew")
        fields = ttk.Frame(prompt_frame, style="App.TFrame")
        fields.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        for column, (label, variable) in enumerate((
            ("Width", self._width_var), ("Height", self._height_var), ("Seed (optional)", self._seed_var)
        )):
            ttk.Label(fields, text=label).grid(row=0, column=column * 2, sticky="w", padx=(0, 4))
            ttk.Entry(fields, textvariable=variable, width=12).grid(row=0, column=column * 2 + 1, sticky="w", padx=(0, 14))
        controls = ttk.Frame(self, style="App.TFrame")
        controls.grid(row=5, column=0, sticky="ew")
        self._generate_button = ttk.Button(controls, text="Generate Image", style="Primary.TButton", command=self.generate)
        self._generate_button.pack(side="left")
        self._cancel_button = ttk.Button(controls, text="Cancel", command=self.cancel, state="disabled")
        self._cancel_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Open Visual Assets", style="Secondary.TButton", command=self._on_open_assets).pack(side="right")
        self._progress = ttk.Progressbar(self, mode="indeterminate", length=420)
        self._progress.grid(row=6, column=0, sticky="ew", pady=(12, 4))
        ttk.Label(self, textvariable=self._status, style="Muted.TLabel", wraplength=980).grid(
            row=7, column=0, sticky="w"
        )
        ttk.Label(
            self,
            text="Low-memory profile: one image, maximum 512×512, CPU backend. "
                 "Model files have their own licenses; verify the model license before use.",
            style="Muted.TLabel", wraplength=980,
        ).grid(row=8, column=0, sticky="w", pady=(8, 0))

    def _load_settings(self):
        try:
            settings = load_local_image_generation_settings(self._settings_path)
        except VisualGenerationSettingsError as exc:
            self._status.set(str(exc))
            return
        self._apply_settings(settings)

    def _apply_settings(self, settings: LocalImageGenerationSettings):
        self._executable_var.set(settings.executable_path)
        self._model_var.set(settings.model_path)
        self._threads_var.set(str(settings.threads))
        self._steps_var.set(str(settings.steps))

    def _settings_from_form(self) -> LocalImageGenerationSettings:
        try:
            threads = int(self._threads_var.get())
            steps = int(self._steps_var.get())
        except (TypeError, ValueError):
            raise VisualGenerationSettingsError("CPU threads and steps must be whole numbers") from None
        return LocalImageGenerationSettings(
            executable_path=self._executable_var.get().strip(),
            model_path=self._model_var.get().strip(),
            threads=threads,
            steps=steps,
        )

    def save_settings(self):
        if self._running:
            return
        try:
            settings = self._settings_from_form()
            save_local_image_generation_settings(self._settings_path, settings)
            self._apply_settings(settings)
            self.refresh_provider_status()
            self._status.set("Local image-generation settings saved on this device.")
        except (VisualGenerationSettingsError, OSError) as exc:
            self._status.set(str(exc))

    def _browse_executable(self):
        path = filedialog.askopenfilename(
            title="Select stable-diffusion.cpp CLI",
            filetypes=(("Windows executable", "*.exe"), ("All files", "*.*")),
        )
        if path:
            self._executable_var.set(path)

    def _browse_model(self):
        path = filedialog.askopenfilename(
            title="Select a compatible local model",
            filetypes=(("Model files", "*.gguf *.safetensors *.ckpt"), ("All files", "*.*")),
        )
        if path:
            self._model_var.set(path)

    def refresh_provider_status(self):
        try:
            settings = self._settings_from_form()
            provider = StableDiffusionCppProvider(
                settings.executable_path, settings.model_path,
                threads=settings.threads, steps=settings.steps,
            )
            self._provider = provider
            self._runtime = VisualGenerationRuntime(self._library, [provider])
            if provider.descriptor.available:
                self._provider_status.configure(text="Ready • local CPU", foreground="#16803c")
                self._status.set("Provider ready. Generation runs locally; no network or API key is used.")
                self._generate_button.configure(state="normal" if not self._running else "disabled")
            else:
                self._provider_status.configure(text="Setup required", foreground="#a16207")
                self._status.set(provider.descriptor.unavailable_reason)
                self._generate_button.configure(state="disabled")
        except (VisualGenerationSettingsError, ValueError, OSError) as exc:
            self._provider = None
            self._runtime = None
            self._provider_status.configure(text="Invalid setup", foreground="#b91c1c")
            self._status.set(str(exc))
            self._generate_button.configure(state="disabled")

    def generate(self):
        if self._running:
            return
        if self._runtime is None or self._provider is None:
            self.refresh_provider_status()
        if self._runtime is None or self._provider is None or not self._provider.descriptor.available:
            self._status.set("Configure a valid local executable and model before generating.")
            return
        prompt = self._prompt.get("1.0", "end").strip()
        negative = self._negative.get("1.0", "end").strip()
        if not prompt:
            self._status.set("Enter an image prompt first.")
            return
        try:
            width = int(self._width_var.get())
            height = int(self._height_var.get())
            seed_text = self._seed_var.get().strip()
            seed = int(seed_text) if seed_text else None
            request = VisualGenerationRequest(
                request_id=uuid.uuid4().hex[:16],
                scene_id="manual-image",
                prompt=prompt,
                negative_prompt=negative,
                model_id=StableDiffusionCppProvider.MODEL_ID,
                width=width,
                height=height,
                output_format="png",
                image_count=1,
                seed=seed,
            )
        except (TypeError, ValueError) as exc:
            self._status.set(f"Invalid generation request: {exc}")
            return
        self._running = True
        self._cancel_event = threading.Event()
        self._generate_button.configure(state="disabled")
        self._cancel_button.configure(state="normal")
        self._progress.start(12)
        self._status.set("Starting local CPU generation…")

        def report(event: VisualGenerationProgress):
            self._bridge.dispatch(self._on_progress, event)

        self._bridge.run_coroutine(
            asyncio.to_thread(
                self._runtime.generate, request, StableDiffusionCppProvider.PROVIDER_ID,
                cancel_event=self._cancel_event, progress=report,
            ),
            on_success=self._on_success,
            on_error=self._on_error,
        )

    def _on_progress(self, event: VisualGenerationProgress):
        if self._running:
            detail = f" • {event.completed}/{event.total}" if event.total else ""
            self._status.set(f"{event.stage.title()}: {event.message or 'Working'}{detail}")

    def _on_success(self, result):
        self._finish()
        names = ", ".join(asset.asset_id for asset in result.assets)
        self._status.set(f"Generated and imported {len(result.assets)} image(s): {names}")

    def _on_error(self, error: Exception):
        self._finish()
        self._status.set(f"Generation failed: {error}")

    def _finish(self):
        self._running = False
        self._cancel_event = None
        self._progress.stop()
        self._cancel_button.configure(state="disabled")
        self.refresh_provider_status()

    def cancel(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self._status.set("Cancellation requested…")

    def shutdown(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
