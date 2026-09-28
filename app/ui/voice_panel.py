from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import List, Optional

from app.core.async_bridge import AsyncBridge
from app.core.config import AppConfig
from app.core.constants import SPEED_PRESETS
from app.core.exceptions import TTSProviderError
from app.core.filenames import safe_filename
from app.core.logger import get_logger
from app.models.voice import Voice
from app.tts.manager import TTSManager
from app.tts.base import SynthResult
from app.audio.player import AudioPlayer

logger = get_logger("ui.voice_panel")

_LANGUAGE_LABELS = {
    "bn": "Bengali",
    "en": "English",
}

_ALL_LANGUAGES = "All Languages"
_ALL_GENDERS = "All Genders"


def _language_label(prefix: str) -> str:
    return _LANGUAGE_LABELS.get(prefix, prefix)


class VoicePanel(ttk.Frame):
    """Voice Library (discovery/filter/preview) + a functional
    text-to-speech generation lab, backed by TTSManager. This is the
    Phase 2 working slice; the full scene-based script editor and the
    dedicated Voice Settings panel (pitch/volume/style) land in Phase 3+.
    """

    def __init__(
        self,
        master: tk.Widget,
        tts_manager: TTSManager,
        async_bridge: AsyncBridge,
        config: AppConfig,
        palette: dict,
        on_status: Optional[callable] = None,
    ) -> None:
        super().__init__(master, style="App.TFrame")
        self._tts_manager = tts_manager
        self._bridge = async_bridge
        self._config = config
        self._palette = palette
        self._on_status = on_status or (lambda text: None)
        self._player = AudioPlayer()

        self._all_voices: List[Voice] = []
        self._filtered_voices: List[Voice] = []
        self._selected_voice: Optional[Voice] = None
        self._busy = False
        self._output_dir = config.output_dir

        self._build_layout()
        self._load_voices(initial=True)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Voice", style="PageTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=24, pady=(24, 4)
        )

        library = ttk.Frame(self, style="App.TFrame")
        library.grid(row=1, column=0, sticky="nsew", padx=(24, 12), pady=(0, 16))
        library.rowconfigure(3, weight=1)
        library.columnconfigure(0, weight=1)
        self._build_library(library)

        generation = ttk.Frame(self, style="App.TFrame")
        generation.grid(row=1, column=1, sticky="nsew", padx=(12, 24), pady=(0, 16))
        generation.columnconfigure(0, weight=1)
        self._build_generation(generation)

    def _build_library(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Voice Library", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        provider_row = ttk.Frame(parent, style="App.TFrame")
        provider_row.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(provider_row, text="Provider:", style="Muted.TLabel").pack(side="left")
        self._provider_var = tk.StringVar(value=self._tts_manager.get_provider_name())
        provider_combo = ttk.Combobox(
            provider_row,
            textvariable=self._provider_var,
            values=[self._tts_manager.get_provider_name()],
            state="readonly",
            style="App.TCombobox",
            width=24,
        )
        provider_combo.pack(side="left", padx=(8, 0))

        filters_row = ttk.Frame(parent, style="App.TFrame")
        filters_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(filters_row, text="Language:", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self._language_var = tk.StringVar(value=_ALL_LANGUAGES)
        self._language_combo = ttk.Combobox(
            filters_row, textvariable=self._language_var, state="readonly",
            style="App.TCombobox", width=16, values=[_ALL_LANGUAGES],
        )
        self._language_combo.grid(row=0, column=1, padx=(8, 16))
        self._language_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        ttk.Label(filters_row, text="Gender:", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self._gender_var = tk.StringVar(value=_ALL_GENDERS)
        self._gender_combo = ttk.Combobox(
            filters_row, textvariable=self._gender_var, state="readonly",
            style="App.TCombobox", width=14, values=[_ALL_GENDERS],
        )
        self._gender_combo.grid(row=0, column=3, padx=(8, 16))
        self._gender_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())

        self._refresh_btn = ttk.Button(
            filters_row, text="Refresh Voices", style="Secondary.TButton",
            command=lambda: self._load_voices(force_refresh=True),
        )
        self._refresh_btn.grid(row=0, column=4)

        tree_frame = ttk.Frame(parent, style="App.TFrame")
        tree_frame.grid(row=3, column=0, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        columns = ("name", "language", "gender")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", style="Voice.Treeview", selectmode="browse"
        )
        self._tree.heading("name", text="Voice")
        self._tree.heading("language", text="Language")
        self._tree.heading("gender", text="Gender")
        self._tree.column("name", width=180)
        self._tree.column("language", width=90, anchor="center")
        self._tree.column("gender", width=80, anchor="center")
        self._tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        selection_row = ttk.Frame(parent, style="App.TFrame")
        selection_row.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self._selected_label = ttk.Label(selection_row, text="No voice selected.", style="Muted.TLabel")
        self._selected_label.pack(side="left")

        self._preview_btn = ttk.Button(
            selection_row, text="\u25b6 Preview", style="Secondary.TButton",
            command=self._on_preview_click, state="disabled",
        )
        self._preview_btn.pack(side="right")

        self._library_status = ttk.Label(parent, text="Loading voices...", style="Muted.TLabel")
        self._library_status.grid(row=5, column=0, sticky="w", pady=(8, 0))

    def _build_generation(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Generate Speech", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        self._text_widget = tk.Text(
            parent, height=10, wrap="word", font=("Segoe UI", 10),
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            insertbackground=self._palette["fg"], relief="flat", padx=8, pady=8,
        )
        self._text_widget.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        controls_row = ttk.Frame(parent, style="App.TFrame")
        controls_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(controls_row, text="Speed:", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self._speed_var = tk.StringVar(value=f"{self._config.default_speed:.2f}x")
        speed_values = [f"{s:.2f}x" for s in SPEED_PRESETS]
        speed_combo = ttk.Combobox(
            controls_row, textvariable=self._speed_var, values=speed_values,
            state="readonly", style="App.TCombobox", width=8,
        )
        speed_combo.grid(row=0, column=1, padx=(8, 16))

        ttk.Label(controls_row, text="Output folder:", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self._output_dir_var = tk.StringVar(value=str(self._output_dir))
        output_entry = ttk.Entry(controls_row, textvariable=self._output_dir_var, state="readonly", width=26)
        output_entry.grid(row=0, column=3, padx=(8, 8))
        ttk.Button(
            controls_row, text="Browse...", style="Secondary.TButton", command=self._on_browse_output_dir
        ).grid(row=0, column=4)

        actions_row = ttk.Frame(parent, style="App.TFrame")
        actions_row.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._generate_btn = ttk.Button(
            actions_row, text="Generate", style="Primary.TButton", command=self._on_generate_click
        )
        self._generate_btn.pack(side="left")
        self._open_folder_btn = ttk.Button(
            actions_row, text="Open Output Folder", style="Secondary.TButton",
            command=self._on_open_output_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(8, 0))

        self._progress = ttk.Progressbar(
            parent, mode="indeterminate", style="App.Horizontal.TProgressbar"
        )
        self._progress.grid(row=4, column=0, sticky="ew", pady=(0, 8))

        self._generation_status = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=480, justify="left")
        self._generation_status.grid(row=5, column=0, sticky="w")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, palette: dict) -> None:
        """Called by MainWindow on theme toggle. ttk widgets restyle
        themselves automatically; only raw tk.Text needs manual recoloring."""
        self._palette = palette
        self._text_widget.configure(
            background=palette["field_bg"], foreground=palette["fg"], insertbackground=palette["fg"]
        )

    # ------------------------------------------------------------------
    # Voice loading / filtering
    # ------------------------------------------------------------------

    def _load_voices(self, force_refresh: bool = False, initial: bool = False) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._library_status.configure(text="Loading voices...", style="Muted.TLabel")
        self._on_status("Loading voices...")

        self._bridge.run_coroutine(
            self._tts_manager.list_voices(force_refresh=force_refresh),
            on_success=self._on_voices_loaded,
            on_error=self._on_voices_error,
        )

    def _on_voices_loaded(self, voices: List[Voice]) -> None:
        self._set_busy(False)
        self._all_voices = voices

        prefixes = sorted({v.language.split("-")[0] for v in voices})
        language_values = [_ALL_LANGUAGES] + [_language_label(p) for p in prefixes]
        self._language_combo.configure(values=language_values)

        genders = sorted({v.gender for v in voices if v.gender})
        gender_values = [_ALL_GENDERS] + genders
        self._gender_combo.configure(values=gender_values)

        self._library_status.configure(text=f"{len(voices)} voices loaded.", style="Muted.TLabel")
        self._on_status(f"{len(voices)} voices loaded.")
        self._apply_filters()

    def _on_voices_error(self, error: Exception) -> None:
        self._set_busy(False)
        message = str(error) if isinstance(error, TTSProviderError) else f"Unexpected error: {error}"
        self._library_status.configure(text=message, style="Error.TLabel")
        self._on_status("Failed to load voices.")
        logger.error("Voice loading failed: %s", error)

    def _apply_filters(self) -> None:
        language_label = self._language_var.get()
        gender = self._gender_var.get()

        prefix_lookup = {_language_label(p): p for p in {v.language.split("-")[0] for v in self._all_voices}}
        target_prefix = prefix_lookup.get(language_label)

        filtered = self._all_voices
        if language_label != _ALL_LANGUAGES and target_prefix:
            filtered = [v for v in filtered if v.language.split("-")[0] == target_prefix]
        if gender != _ALL_GENDERS:
            filtered = [v for v in filtered if v.gender == gender]

        self._filtered_voices = filtered
        self._populate_tree(filtered)

    def _populate_tree(self, voices: List[Voice]) -> None:
        self._tree.delete(*self._tree.get_children())
        for voice in voices:
            self._tree.insert(
                "", "end", iid=voice.id,
                values=(voice.name, voice.language, voice.gender or "Unknown"),
            )

    def _on_tree_select(self, _event=None) -> None:
        selection = self._tree.selection()
        if not selection:
            self._selected_voice = None
            self._selected_label.configure(text="No voice selected.")
            self._preview_btn.configure(state="disabled")
            return
        voice_id = selection[0]
        voice = next((v for v in self._filtered_voices if v.id == voice_id), None)
        self._selected_voice = voice
        if voice:
            self._selected_label.configure(
                text=f"Selected: {voice.name} ({voice.language}, {voice.gender or 'Unknown'})"
            )
            self._preview_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _on_preview_click(self) -> None:
        if self._busy or not self._selected_voice:
            return
        voice = self._selected_voice
        self._set_busy(True)
        self._library_status.configure(text=f"Generating preview for {voice.name}...", style="Muted.TLabel")
        self._on_status(f"Generating preview for {voice.name}...")

        preview_path = self._config.previews_dir / safe_filename(f"preview_{voice.id}", "mp3")
        self._bridge.run_coroutine(
            self._tts_manager.preview_voice(voice.id, preview_path),
            on_success=self._on_preview_ready,
            on_error=self._on_preview_error,
        )

    def _on_preview_ready(self, result: SynthResult) -> None:
        self._set_busy(False)
        self._library_status.configure(text="Playing preview...", style="Success.TLabel")
        self._on_status("Playing voice preview.")
        self._player.play(
            Path(result.audio_path),
            on_error=lambda exc: self._on_playback_error(exc),
        )

    def _on_preview_error(self, error: Exception) -> None:
        self._set_busy(False)
        message = str(error) if isinstance(error, TTSProviderError) else f"Unexpected error: {error}"
        self._library_status.configure(text=f"Preview failed: {message}", style="Error.TLabel")
        self._on_status("Voice preview failed.")
        logger.error("Preview failed: %s", error)

    def _on_playback_error(self, error: Exception) -> None:
        self._library_status.configure(text=f"Playback failed: {error}", style="Error.TLabel")
        logger.error("Playback failed: %s", error)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _on_browse_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=str(self._output_dir))
        if chosen:
            self._output_dir = Path(chosen)
            self._output_dir_var.set(chosen)

    def _on_open_output_folder(self) -> None:
        import os
        import sys

        try:
            if sys.platform == "win32":
                os.startfile(str(self._output_dir))  # noqa: S606 - user-chosen local folder
            else:
                self._generation_status.configure(
                    text=f"Output folder: {self._output_dir}", style="Muted.TLabel"
                )
        except OSError as exc:
            self._generation_status.configure(text=f"Could not open folder: {exc}", style="Error.TLabel")

    def _on_generate_click(self) -> None:
        if self._busy:
            return
        if not self._selected_voice:
            self._generation_status.configure(text="Please select a voice from the library first.", style="Error.TLabel")
            return

        text = self._text_widget.get("1.0", "end").strip()
        if not text:
            self._generation_status.configure(text="Please enter some text to generate speech.", style="Error.TLabel")
            return

        speed = float(self._speed_var.get().rstrip("x"))
        voice = self._selected_voice
        output_path = self._output_dir / safe_filename(voice.id, "mp3")

        self._set_busy(True)
        self._progress.start(12)
        self._generation_status.configure(text="Generating speech...", style="Muted.TLabel")
        self._on_status(f"Generating speech with {voice.name}...")

        self._bridge.run_coroutine(
            self._tts_manager.generate(text, voice.id, output_path, speed=speed),
            on_success=self._on_generation_success,
            on_error=self._on_generation_error,
        )

    def _on_generation_success(self, result: SynthResult) -> None:
        self._set_busy(False)
        self._progress.stop()
        self._generation_status.configure(text=f"Done: {result.audio_path}", style="Success.TLabel")
        self._on_status("Audio generated.")
        logger.info("Generated audio: %s", result.audio_path)

    def _on_generation_error(self, error: Exception) -> None:
        self._set_busy(False)
        self._progress.stop()
        message = str(error) if isinstance(error, TTSProviderError) else f"Unexpected error: {error}"
        self._generation_status.configure(text=f"Generation failed: {message}", style="Error.TLabel")
        self._on_status("Speech generation failed.")
        logger.error("Generation failed: %s", error)

    # ------------------------------------------------------------------
    # Busy state
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self._refresh_btn.configure(state=state)
        self._generate_btn.configure(state=state)
        if not busy and self._selected_voice:
            self._preview_btn.configure(state="normal")
        elif busy:
            self._preview_btn.configure(state="disabled")