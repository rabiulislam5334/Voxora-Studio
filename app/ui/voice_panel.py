from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from app.audio.player import AudioPlayer, PlaybackState, VoicePreviewPlayer
from app.audio.session import GeneratedAudioSession
from app.core.async_bridge import AsyncBridge
from app.core.config import AppConfig
from app.core.constants import SPEED_PRESETS
from app.core.exceptions import AudioProcessingError, TTSProviderError
from app.core.filenames import safe_filename
from app.core.logger import get_logger
from app.ui.theme import style_combobox_dropdown
from app.models.voice import Voice
from app.tts.manager import TTSManager
from app.tts.base import SynthResult

logger = get_logger("ui.voice_panel")

_LANGUAGE_LABELS = {
    "bn": "Bengali",
    "en": "English",
}

_ALL_LANGUAGES = "All Languages"
_ALL_GENDERS = "All Genders"

_UI_REFRESH_MS = 200


def _language_label(prefix: str) -> str:
    return _LANGUAGE_LABELS.get(prefix, prefix)


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


class VoicePanel(ttk.Frame):
    """Voice Library (discovery/filter/preview) + a functional
    text-to-speech generation lab with a full in-app audio player
    (Phase 2.1): play/pause/resume/stop/seek/volume, plus an explicit
    Save As export step. Generation always writes to one deterministic
    app-owned temp folder (see app/audio/session.py) -- there is no
    longer a separate, independently-editable "output folder" field for
    generation to silently disagree with; Save As is the only way audio
    leaves the app's own storage.
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

        self._preview_player = VoicePreviewPlayer()
        self._audio_player = AudioPlayer()
        self._session = GeneratedAudioSession(config.generated_audio_dir)

        self._all_voices: List[Voice] = []
        self._filtered_voices: List[Voice] = []
        self._selected_voice: Optional[Voice] = None
        self._busy = False
        self._seeking = False
        self._ui_update_job: Optional[str] = None
        self._player_controls_enabled = False

        self._build_layout()
        self._load_voices(initial=True)
        self._schedule_ui_update()

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
        self._provider_combo = ttk.Combobox(
            provider_row,
            textvariable=self._provider_var,
            values=[self._tts_manager.get_provider_name()],
            state="readonly",
            style="App.TCombobox",
            width=24,
        )
        self._provider_combo.pack(side="left", padx=(8, 0))
        style_combobox_dropdown(self._provider_combo, self._palette)

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
        style_combobox_dropdown(self._language_combo, self._palette)

        ttk.Label(filters_row, text="Gender:", style="Muted.TLabel").grid(row=0, column=2, sticky="w")
        self._gender_var = tk.StringVar(value=_ALL_GENDERS)
        self._gender_combo = ttk.Combobox(
            filters_row, textvariable=self._gender_var, state="readonly",
            style="App.TCombobox", width=18, values=[_ALL_GENDERS],
        )
        self._gender_combo.grid(row=0, column=3, padx=(8, 16))
        self._gender_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_filters())
        style_combobox_dropdown(self._gender_combo, self._palette)

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
            selection_row, text="\u25b6 Preview", style="Primary.TButton",
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
            parent, height=9, wrap="word", font=("Segoe UI", 10),
            background=self._palette["field_bg"], foreground=self._palette["fg"],
            insertbackground=self._palette["fg"], relief="flat", padx=8, pady=8,
            highlightthickness=1, highlightbackground=self._palette["border"],
            highlightcolor=self._palette["accent"],
        )
        self._text_widget.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        controls_row = ttk.Frame(parent, style="App.TFrame")
        controls_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(controls_row, text="Speed:", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self._speed_var = tk.StringVar(value=f"{self._config.default_speed:.2f}x")
        speed_values = [f"{s:.2f}x" for s in SPEED_PRESETS]
        self._speed_combo = ttk.Combobox(
            controls_row, textvariable=self._speed_var, values=speed_values,
            state="readonly", style="App.TCombobox", width=8,
        )
        self._speed_combo.grid(row=0, column=1, padx=(8, 0))
        style_combobox_dropdown(self._speed_combo, self._palette)

        self._generate_btn = ttk.Button(
            controls_row, text="Generate", style="Primary.TButton", command=self._on_generate_click
        )
        self._generate_btn.grid(row=0, column=2, padx=(16, 0))

        self._progress = ttk.Progressbar(
            parent, mode="indeterminate", style="App.Horizontal.TProgressbar"
        )
        self._progress.grid(row=3, column=0, sticky="ew", pady=(0, 4))

        self._generation_status = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=480, justify="left")
        self._generation_status.grid(row=4, column=0, sticky="w", pady=(0, 12))

        self._build_player(parent)

    def _build_player(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent, orient="horizontal").grid(row=5, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(parent, text="Generated Audio Player", style="SectionTitle.TLabel").grid(
            row=6, column=0, sticky="w", pady=(0, 8)
        )

        transport_row = ttk.Frame(parent, style="App.TFrame")
        transport_row.grid(row=7, column=0, sticky="ew", pady=(0, 8))

        self._play_pause_btn = ttk.Button(
            transport_row, text="\u25b6 Play", style="Primary.TButton",
            command=self._on_play_pause_click, state="disabled",
        )
        self._play_pause_btn.pack(side="left")

        self._stop_btn = ttk.Button(
            transport_row, text="\u25a0 Stop", style="Secondary.TButton",
            command=self._on_stop_click, state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(8, 0))

        self._save_as_btn = ttk.Button(
            transport_row, text="Save As...", style="Secondary.TButton",
            command=self._on_save_as_click, state="disabled",
        )
        self._save_as_btn.pack(side="left", padx=(8, 0))

        self._regenerate_btn = ttk.Button(
            transport_row, text="Regenerate", style="Secondary.TButton",
            command=self._on_generate_click, state="disabled",
        )
        self._regenerate_btn.pack(side="left", padx=(8, 0))

        seek_row = ttk.Frame(parent, style="App.TFrame")
        seek_row.grid(row=8, column=0, sticky="ew", pady=(0, 4))
        seek_row.columnconfigure(0, weight=1)

        self._seek_scale = ttk.Scale(
            seek_row, from_=0, to=1, orient="horizontal", command=self._on_seek_drag
        )
        self._seek_scale.grid(row=0, column=0, sticky="ew")
        self._seek_scale.state(["disabled"])
        self._seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
        self._seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        time_volume_row = ttk.Frame(parent, style="App.TFrame")
        time_volume_row.grid(row=9, column=0, sticky="ew", pady=(0, 8))

        self._time_label = ttk.Label(time_volume_row, text="00:00 / 00:00", style="Muted.TLabel")
        self._time_label.pack(side="left")

        ttk.Label(time_volume_row, text="Volume:", style="Muted.TLabel").pack(side="left", padx=(24, 4))
        self._volume_scale = ttk.Scale(
            time_volume_row, from_=0, to=100, orient="horizontal",
            command=self._on_volume_change, length=120,
        )
        self._volume_scale.set(100)
        self._volume_scale.pack(side="left")

        self._playback_status = ttk.Label(parent, text="Ready", style="Muted.TLabel")
        self._playback_status.grid(row=10, column=0, sticky="w")

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, palette: dict) -> None:
        """Called by MainWindow on theme toggle. ttk widgets restyle
        themselves automatically; raw tk.Text needs manual recoloring, and
        each Combobox's popup listbox (outside the ttk style system -- see
        style_combobox_dropdown) must be explicitly re-colored too, or it
        keeps showing whatever theme was active when it was first opened."""
        self._palette = palette
        self._text_widget.configure(
            background=palette["field_bg"], foreground=palette["fg"], insertbackground=palette["fg"],
            highlightbackground=palette["border"], highlightcolor=palette["accent"],
        )
        for combo in (self._provider_combo, self._language_combo, self._gender_combo, self._speed_combo):
            style_combobox_dropdown(combo, palette)

    # ------------------------------------------------------------------
    # Voice loading / filtering  (unchanged from Phase 2)
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
    # Preview (independent audio channel -- never touches the main player)
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
        self._preview_player.play(
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
        self._library_status.configure(text=f"Preview playback failed: {error}", style="Error.TLabel")
        logger.error("Preview playback failed: %s", error)

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

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

        # Release any lock on the currently-loaded (about to be replaced)
        # file BEFORE we start generating -- this is what makes it safe
        # to delete the old temp file once the new one lands.
        self._audio_player.stop()
        self._set_player_controls_enabled(False)

        output_path = self._config.generated_audio_dir / safe_filename(voice.id, "mp3")

        self._set_busy(True)
        self._progress.start(12)
        self._generation_status.configure(text="Generating speech...", style="Muted.TLabel")
        self._playback_status.configure(text="Generating...", style="Muted.TLabel")
        self._on_status(f"Generating speech with {voice.name}...")

        self._bridge.run_coroutine(
            self._tts_manager.generate(text, voice.id, output_path, speed=speed),
            on_success=self._on_generation_success,
            on_error=self._on_generation_error,
        )

    def _on_generation_success(self, result: SynthResult) -> None:
        self._set_busy(False)
        self._progress.stop()
        new_path = Path(result.audio_path)

        try:
            duration = self._audio_player.load(new_path)
        except AudioProcessingError as exc:
            logger.warning("Generated audio saved but could not be loaded for playback: %s", exc)
            self._session.adopt_new_generation(new_path)
            self._generation_status.configure(
                text="Audio generated, but in-app playback is unavailable on this system "
                     f"({exc}). You can still use Save As.",
                style="Error.TLabel",
            )
            self._set_player_controls_enabled(False)
            self._save_as_btn.configure(state="normal")
            self._on_status("Audio generated (playback unavailable).")
            return

        self._session.adopt_new_generation(new_path)
        self._seek_scale.configure(to=max(duration, 0.1))
        self._seek_scale.set(0)
        self._set_player_controls_enabled(True)
        self._generation_status.configure(text="Audio generated. Not yet saved.", style="Success.TLabel")
        self._on_status("Audio generated.")
        logger.info("Generated audio: %s", new_path)

    def _on_generation_error(self, error: Exception) -> None:
        self._set_busy(False)
        self._progress.stop()
        message = str(error) if isinstance(error, TTSProviderError) else f"Unexpected error: {error}"
        self._generation_status.configure(text=f"Generation failed: {message}", style="Error.TLabel")
        self._playback_status.configure(text="Ready", style="Muted.TLabel")
        self._on_status("Speech generation failed.")
        logger.error("Generation failed: %s", error)

    # ------------------------------------------------------------------
    # Player transport
    # ------------------------------------------------------------------

    def _set_player_controls_enabled(self, enabled: bool) -> None:
        self._player_controls_enabled = enabled
        state = "normal" if enabled else "disabled"
        self._play_pause_btn.configure(state=state)
        self._stop_btn.configure(state=state)
        self._save_as_btn.configure(state=state)
        self._regenerate_btn.configure(state="normal" if self._selected_voice else "disabled")
        if enabled:
            self._seek_scale.state(["!disabled"])
        else:
            self._seek_scale.state(["disabled"])

    def _on_play_pause_click(self) -> None:
        if not self._player_controls_enabled:
            return
        status = self._audio_player.get_status()
        try:
            if status.state == PlaybackState.PLAYING:
                self._audio_player.pause()
            elif status.state == PlaybackState.PAUSED:
                self._audio_player.resume()
            else:
                self._audio_player.play(start_seconds=0.0)
        except AudioProcessingError as exc:
            self._playback_status.configure(text=str(exc), style="Error.TLabel")
            logger.error("Playback failed: %s", exc)

    def _on_stop_click(self) -> None:
        if not self._player_controls_enabled:
            return
        self._audio_player.stop()

    def _on_seek_press(self, _event=None) -> None:
        if self._player_controls_enabled:
            self._seeking = True

    def _on_seek_drag(self, _value) -> None:
        # Live time-label feedback while dragging; the actual seek only
        # happens on release so we don't spam pygame with play() calls.
        if self._seeking:
            self._time_label.configure(
                text=f"{_format_time(float(_value))} / {_format_time(self._audio_player.get_status().duration_seconds)}"
            )

    def _on_seek_release(self, _event=None) -> None:
        if not self._seeking:
            return
        self._seeking = False
        if not self._player_controls_enabled:
            return
        try:
            self._audio_player.seek(self._seek_scale.get())
        except AudioProcessingError as exc:
            self._playback_status.configure(text=str(exc), style="Error.TLabel")

    def _on_volume_change(self, value: str) -> None:
        try:
            self._audio_player.set_volume(float(value) / 100.0)
        except AudioProcessingError:
            pass  # backend unavailable -- silently ignored, already reported elsewhere

    def _on_save_as_click(self) -> None:
        if self._session.current_path is None:
            self._generation_status.configure(text="There is no generated audio to save yet.", style="Error.TLabel")
            return

        suggested_name = f"{self._selected_voice.id}.mp3" if self._selected_voice else "narration.mp3"
        destination = filedialog.asksaveasfilename(
            title="Save Generated Audio As",
            defaultextension=".mp3",
            filetypes=[("MP3 Audio", "*.mp3")],
            initialdir=str(self._config.output_dir),
            initialfile=suggested_name,
        )
        if not destination:
            self._generation_status.configure(text="Save cancelled.", style="Muted.TLabel")
            return

        try:
            saved_path = self._session.save_as(Path(destination))
        except AudioProcessingError as exc:
            self._generation_status.configure(text=f"Save failed: {exc}", style="Error.TLabel")
            logger.error("Save As failed: %s", exc)
            return

        self._generation_status.configure(text=f"Saved to: {saved_path}", style="Success.TLabel")
        self._on_status("Audio saved.")

    # ------------------------------------------------------------------
    # Periodic playback UI refresh
    # ------------------------------------------------------------------

    def _schedule_ui_update(self) -> None:
        self._update_playback_ui()
        self._ui_update_job = self.after(_UI_REFRESH_MS, self._schedule_ui_update)

    def _update_playback_ui(self) -> None:
        status = self._audio_player.get_status()

        if not self._seeking:
            self._seek_scale.set(status.position_seconds)
            self._time_label.configure(
                text=f"{_format_time(status.position_seconds)} / {_format_time(status.duration_seconds)}"
            )

        if status.state == PlaybackState.PLAYING:
            self._play_pause_btn.configure(text="\u23f8 Pause")
            self._playback_status.configure(text="Playing", style="PlaybackActive.TLabel")
        elif status.state == PlaybackState.PAUSED:
            self._play_pause_btn.configure(text="\u25b6 Play")
            self._playback_status.configure(text="Paused", style="Muted.TLabel")
        else:
            self._play_pause_btn.configure(text="\u25b6 Play")
            if self._player_controls_enabled:
                self._playback_status.configure(text="Stopped", style="Muted.TLabel")

    # ------------------------------------------------------------------
    # Busy state (voice loading / generation in flight)
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

    # ------------------------------------------------------------------
    # Lifecycle hooks called by MainWindow
    # ------------------------------------------------------------------

    def confirm_close(self) -> bool:
        """Return False to veto closing the application."""
        if self._session.current_path is not None and not self._session.is_saved:
            return messagebox.askyesno(
                "Unsaved Audio",
                "You have generated audio that hasn't been saved with "
                "Save As.\n\nClose AI YouTube Voice Studio anyway?",
            )
        return True

    def shutdown(self) -> None:
        if self._ui_update_job is not None:
            try:
                self.after_cancel(self._ui_update_job)
            except Exception:
                pass
            self._ui_update_job = None
        self._audio_player.shutdown()
        self._session.cleanup()