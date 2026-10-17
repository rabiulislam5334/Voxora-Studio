from __future__ import annotations

import asyncio
import re
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Protocol

from app.audio.ffmpeg_tool import FFmpegStatus, FFmpegTool
from app.audio.player import AudioPlayer, PlaybackState, VoicePreviewPlayer
from app.audio.session import GeneratedAudioSession
from app.cache.manager import NarrationCache
from app.core.async_bridge import AsyncBridge
from app.core.config import AppConfig
from app.core.constants import APP_NAME
from app.core.exceptions import (
    AudioProcessingError,
    ConfigurationError,
    FFmpegError,
    GenerationCancelled,
    NarrationError,
    TTSProviderError,
)
from app.core.filenames import safe_filename
from app.core.logger import get_logger
from app.core.settings_store import SettingsStore
from app.ui.theme import style_combobox_dropdown
from app.models.scene import Scene
from app.models.voice import Voice
from app.models.voice_preset import (
    PAUSE_MS_MAX,
    PAUSE_MS_MIN,
    PITCH_HZ_MAX,
    PITCH_HZ_MIN,
    RATE_MAX,
    RATE_MIN,
    VOLUME_PERCENT_MAX,
    VOLUME_PERCENT_MIN,
    VoicePreset,
    validate_preset,
)
from app.tts.manager import TTSManager
from app.tts.base import SynthResult
from app.tts.preset_store import PresetStore
from app.workers.cancel import CancelToken
from app.workers.narration import (
    NarrationJob,
    NarrationResult,
    ProgressEvent,
    SceneRequest,
    build_scene_request,
)

logger = get_logger("ui.voice_panel")

_LANGUAGE_LABELS = {
    "bn": "Bengali",
    "en": "English",
}

_ALL_LANGUAGES = "All Languages"
_ALL_GENDERS = "All Genders"

_UI_REFRESH_MS = 200

_UNSAFE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _language_label(prefix: str) -> str:
    return _LANGUAGE_LABELS.get(prefix, prefix)


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


class NarrationSource(Protocol):
    """What the Voice page needs from the Script page (Phase 5). Read-only:
    the Voice page never edits scenes."""

    def get_project_name(self) -> str: ...

    def get_scenes(self) -> List[Scene]: ...

    def get_selected_scene(self) -> Optional[Scene]: ...


class VoicePanel(ttk.Frame):
    """Voice Library (discovery/filter/preview) + a functional
    text-to-speech generation lab with a full in-app audio player
    (Phase 2.1): play/pause/resume/stop/seek/volume, plus an explicit
    Save As export step. Generation always writes to one deterministic
    app-owned temp folder (see app/audio/session.py) -- there is no
    longer a separate, independently-editable "output folder" field for
    generation to silently disagree with; Save As is the only way audio
    leaves the app's own storage.

    Phase 5 adds scene-by-scene narration (Generate Selected Scene /
    Generate Full Narration) with real pause insertion, cancel/resume and
    FFmpeg-based assembly; results flow into this same player and Save As.
    """

    def __init__(
        self,
        master: tk.Widget,
        tts_manager: TTSManager,
        async_bridge: AsyncBridge,
        config: AppConfig,
        palette: dict,
        on_status: Optional[callable] = None,
        script_source: Optional[NarrationSource] = None,
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
        self._preset_store = PresetStore(config.presets_file)

        # Phase 5: scene-by-scene narration (see app/workers/narration.py).
        self._script_source = script_source
        self._settings_store = SettingsStore(config.settings_file)
        self._ffmpeg = FFmpegTool(self._settings_store)
        self._narration_cache = NarrationCache(config.chunk_cache_dir, config.scene_cache_dir)
        self._narration_job = NarrationJob(
            tts_manager, self._ffmpeg, self._narration_cache, config.temp_dir
        )
        self._narration_running = False
        self._cancel_token: Optional[CancelToken] = None
        self._narration_mp3: Optional[Path] = None
        self._narration_wav: Optional[Path] = None
        self._save_name_hint: Optional[str] = None

        self._all_voices: List[Voice] = []
        self._filtered_voices: List[Voice] = []
        self._selected_voice: Optional[Voice] = None
        self._busy = False
        self._seeking = False
        self._ui_update_job: Optional[str] = None
        self._player_controls_enabled = False

        # Phase 4: the live, currently-edited narration settings -- a
        # fresh COPY of the default preset, so selecting/adjusting never
        # mutates the built-in preset objects themselves.
        self._current_settings: VoicePreset = self._preset_store.list_builtin()[0].copy_with()

        self._build_layout()
        self._apply_settings_to_widgets()
        self._load_voices(initial=True)
        self._detect_ffmpeg()
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
        library.grid(row=1, column=0, sticky="nsew", padx=(24, 12), pady=(0, 8))
        library.rowconfigure(3, weight=1)
        library.columnconfigure(0, weight=1)
        self._build_library(library)

        settings_frame = ttk.Frame(self, style="App.TFrame")
        settings_frame.grid(row=2, column=0, sticky="new", padx=(24, 12), pady=(0, 16))
        settings_frame.columnconfigure(0, weight=1)
        self._build_voice_settings(settings_frame)

        generation = ttk.Frame(self, style="App.TFrame")
        generation.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(12, 24), pady=(0, 16))
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

    def _build_voice_settings(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Voice Settings", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        preset_label_row = ttk.Frame(parent, style="App.TFrame")
        preset_label_row.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(preset_label_row, text="Preset:", style="Muted.TLabel").pack(side="left")
        self._preset_var = tk.StringVar(value=self._current_settings.name)
        self._preset_combo = ttk.Combobox(
            preset_label_row, textvariable=self._preset_var, state="readonly",
            style="App.TCombobox", width=28,
            values=[p.name for p in self._preset_store.list_all()],
        )
        self._preset_combo.pack(side="left", padx=(8, 0), fill="x", expand=True)
        self._preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)
        style_combobox_dropdown(self._preset_combo, self._palette)

        preset_button_row = ttk.Frame(parent, style="App.TFrame")
        preset_button_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(
            preset_button_row, text="Save As...", style="Secondary.TButton", command=self._on_save_preset_click
        ).pack(side="left", padx=(0, 6))
        self._delete_preset_btn = ttk.Button(
            preset_button_row, text="Delete Preset", style="Secondary.TButton",
            command=self._on_delete_preset_click, state="disabled",
        )
        self._delete_preset_btn.pack(side="left")

        self._rate_value_label, self._rate_scale = self._build_slider_row(
            parent, row=3, label="Rate:", from_=RATE_MIN, to=RATE_MAX, command=self._on_rate_change,
        )
        self._pitch_value_label, self._pitch_scale = self._build_slider_row(
            parent, row=4, label="Pitch:", from_=PITCH_HZ_MIN, to=PITCH_HZ_MAX, command=self._on_pitch_change,
        )
        # Named distinctly from the Generated Audio Player's _volume_scale
        # further down -- THIS slider is a SYNTHESIS parameter, baked into
        # the generated file by Edge TTS itself. The player's volume is a
        # PLAYBACK parameter applied live at listening time and never
        # touches the generated file. Kept deliberately separate per the
        # Phase 4 spec ("do not confuse the two").
        self._tts_volume_value_label, self._tts_volume_scale = self._build_slider_row(
            parent, row=5, label="Synth Volume:", from_=VOLUME_PERCENT_MIN, to=VOLUME_PERCENT_MAX,
            command=self._on_tts_volume_change,
        )

        pause_row = ttk.Frame(parent, style="App.TFrame")
        pause_row.grid(row=6, column=0, sticky="ew", pady=(4, 0))

        self._sentence_pause_var = tk.StringVar(value=str(self._current_settings.sentence_pause_ms))
        self._paragraph_pause_var = tk.StringVar(value=str(self._current_settings.paragraph_pause_ms))
        self._scene_pause_var = tk.StringVar(value=str(self._current_settings.scene_pause_ms))

        pause_fields = [
            ("Sentence pause (ms):", self._sentence_pause_var, self._on_sentence_pause_change),
            ("Paragraph pause (ms):", self._paragraph_pause_var, self._on_paragraph_pause_change),
            ("Scene pause (ms):", self._scene_pause_var, self._on_scene_pause_change),
        ]
        for i, (label, var, cmd) in enumerate(pause_fields):
            ttk.Label(pause_row, text=label, style="Muted.TLabel").grid(row=i, column=0, sticky="w", pady=2)
            spin = ttk.Spinbox(
                pause_row, from_=PAUSE_MS_MIN, to=PAUSE_MS_MAX, increment=50,
                textvariable=var, width=8, command=cmd,
            )
            spin.grid(row=i, column=1, sticky="w", padx=(8, 0), pady=2)
            spin.bind("<KeyRelease>", lambda _e, c=cmd: c())

        ttk.Label(
            parent,
            text="Sentence/paragraph/scene pauses become real silence when you use the "
                 "Narration buttons (right). The plain Generate button does not apply them.",
            style="Muted.TLabel", wraplength=320, justify="left",
        ).grid(row=7, column=0, sticky="w", pady=(8, 0))

    def _build_slider_row(self, parent: ttk.Frame, row: int, label: str, from_: float, to: float, command):
        row_frame = ttk.Frame(parent, style="App.TFrame")
        row_frame.grid(row=row, column=0, sticky="ew", pady=4)
        row_frame.columnconfigure(1, weight=1)
        ttk.Label(row_frame, text=label, style="Muted.TLabel", width=13).grid(row=0, column=0, sticky="w")
        scale = ttk.Scale(row_frame, from_=from_, to=to, orient="horizontal", command=command)
        scale.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        value_label = ttk.Label(row_frame, text="", style="Muted.TLabel", width=8)
        value_label.grid(row=0, column=2, sticky="e")
        return value_label, scale

    def _apply_settings_to_widgets(self) -> None:
        """Push self._current_settings into every control -- called on
        init and whenever a preset is selected."""
        s = self._current_settings
        self._rate_scale.set(s.rate)
        self._rate_value_label.configure(text=f"{s.rate:.2f}x")
        self._pitch_scale.set(s.pitch_hz)
        self._pitch_value_label.configure(text=f"{s.pitch_hz:+d}Hz")
        self._tts_volume_scale.set(s.volume_percent)
        self._tts_volume_value_label.configure(text=f"{s.volume_percent:+d}%")
        self._sentence_pause_var.set(str(s.sentence_pause_ms))
        self._paragraph_pause_var.set(str(s.paragraph_pause_ms))
        self._scene_pause_var.set(str(s.scene_pause_ms))

    def _refresh_preset_list(self, select_name: Optional[str] = None) -> None:
        names = [p.name for p in self._preset_store.list_all()]
        self._preset_combo.configure(values=names)
        style_combobox_dropdown(self._preset_combo, self._palette)
        target = select_name if select_name in names else (names[0] if names else None)
        if target:
            self._preset_var.set(target)
            self._on_preset_selected()

    def _on_preset_selected(self, _event=None) -> None:
        name = self._preset_var.get()
        try:
            preset = self._preset_store.get(name)
        except ConfigurationError:
            return
        self._current_settings = preset.copy_with()
        self._apply_settings_to_widgets()
        self._delete_preset_btn.configure(state="disabled" if preset.is_builtin else "normal")
        self._on_status(f"Preset '{preset.name}' applied.")

    def _on_rate_change(self, value: str) -> None:
        rate = round(float(value), 2)
        self._current_settings.rate = rate
        self._rate_value_label.configure(text=f"{rate:.2f}x")

    def _on_pitch_change(self, value: str) -> None:
        pitch = int(round(float(value)))
        self._current_settings.pitch_hz = pitch
        self._pitch_value_label.configure(text=f"{pitch:+d}Hz")

    def _on_tts_volume_change(self, value: str) -> None:
        volume = int(round(float(value)))
        self._current_settings.volume_percent = volume
        self._tts_volume_value_label.configure(text=f"{volume:+d}%")

    def _on_sentence_pause_change(self) -> None:
        self._current_settings.sentence_pause_ms = self._safe_int(
            self._sentence_pause_var.get(), self._current_settings.sentence_pause_ms
        )

    def _on_paragraph_pause_change(self) -> None:
        self._current_settings.paragraph_pause_ms = self._safe_int(
            self._paragraph_pause_var.get(), self._current_settings.paragraph_pause_ms
        )

    def _on_scene_pause_change(self) -> None:
        self._current_settings.scene_pause_ms = self._safe_int(
            self._scene_pause_var.get(), self._current_settings.scene_pause_ms
        )

    @staticmethod
    def _safe_int(value: str, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _on_save_preset_click(self) -> None:
        from tkinter import simpledialog

        default_name = self._current_settings.name if not self._current_settings.is_builtin else "My Preset"
        name = simpledialog.askstring("Save Preset", "Preset name:", initialvalue=default_name, parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        preset = self._current_settings.copy_with(name=name, is_builtin=False)
        try:
            self._preset_store.save_custom(preset)
        except ConfigurationError as exc:
            messagebox.showerror("Save Preset Failed", str(exc))
            return
        self._refresh_preset_list(select_name=name)
        self._on_status(f"Saved preset '{name}'.")

    def _on_delete_preset_click(self) -> None:
        name = self._preset_var.get()
        try:
            preset = self._preset_store.get(name)
        except ConfigurationError:
            return
        if preset.is_builtin:
            return
        if not messagebox.askyesno("Delete Preset", f"Delete custom preset '{name}'?"):
            return
        try:
            self._preset_store.delete_custom(name)
        except ConfigurationError as exc:
            messagebox.showerror("Delete Failed", str(exc))
            return
        self._refresh_preset_list(select_name="Normal Narrator")
        self._on_status(f"Deleted preset '{name}'.")

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

        ttk.Label(
            controls_row, text="Rate/Pitch/Volume now live in the Voice Settings panel on the left.",
            style="Muted.TLabel", wraplength=320, justify="left",
        ).grid(row=0, column=0, sticky="w")

        self._generate_btn = ttk.Button(
            controls_row, text="Generate", style="Primary.TButton", command=self._on_generate_click
        )
        self._generate_btn.grid(row=0, column=1, padx=(16, 0))

        self._progress = ttk.Progressbar(
            parent, mode="indeterminate", style="App.Horizontal.TProgressbar"
        )
        self._progress.grid(row=3, column=0, sticky="ew", pady=(0, 4))

        self._generation_status = ttk.Label(parent, text="", style="Muted.TLabel", wraplength=480, justify="left")
        self._generation_status.grid(row=4, column=0, sticky="w", pady=(0, 12))

        self._build_narration(parent)
        self._build_player(parent)

    def _build_narration(self, parent: ttk.Frame) -> None:
        """Phase 5 controls. They reuse the progress bar and status line
        above (one generation at a time), so this adds only a compact block."""
        block = ttk.Frame(parent, style="App.TFrame")
        block.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(block, text="Narration (scene by scene, real pauses)", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        buttons = ttk.Frame(block, style="App.TFrame")
        buttons.grid(row=1, column=0, sticky="w")
        self._scene_narration_btn = ttk.Button(
            buttons, text="Generate Selected Scene", style="Primary.TButton",
            command=self._on_generate_scene_click, state="disabled",
        )
        self._scene_narration_btn.pack(side="left")
        self._full_narration_btn = ttk.Button(
            buttons, text="Generate Full Narration", style="Primary.TButton",
            command=self._on_generate_full_click, state="disabled",
        )
        self._full_narration_btn.pack(side="left", padx=(8, 0))
        self._cancel_btn = ttk.Button(
            buttons, text="Cancel", style="Secondary.TButton",
            command=self._on_cancel_click, state="disabled",
        )
        self._cancel_btn.pack(side="left", padx=(8, 0))
        self._export_wav_btn = ttk.Button(
            buttons, text="Export WAV...", style="Secondary.TButton",
            command=self._on_export_wav_click, state="disabled",
        )
        self._export_wav_btn.pack(side="left", padx=(8, 0))

        ffmpeg_row = ttk.Frame(block, style="App.TFrame")
        ffmpeg_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        self._ffmpeg_check_btn = ttk.Button(
            ffmpeg_row, text="Check FFmpeg", style="Secondary.TButton", command=self._detect_ffmpeg
        )
        self._ffmpeg_check_btn.pack(side="left")
        self._ffmpeg_path_btn = ttk.Button(
            ffmpeg_row, text="Set Path...", style="Secondary.TButton", command=self._on_set_ffmpeg_path
        )
        self._ffmpeg_path_btn.pack(side="left", padx=(6, 10))
        self._ffmpeg_status_label = ttk.Label(
            ffmpeg_row, text="FFmpeg: checking...", style="Muted.TLabel", wraplength=300, justify="left"
        )
        self._ffmpeg_status_label.pack(side="left", fill="x", expand=True)

    def _build_player(self, parent: ttk.Frame) -> None:
        ttk.Separator(parent, orient="horizontal").grid(row=6, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(parent, text="Generated Audio Player", style="SectionTitle.TLabel").grid(
            row=7, column=0, sticky="w", pady=(0, 8)
        )

        transport_row = ttk.Frame(parent, style="App.TFrame")
        transport_row.grid(row=8, column=0, sticky="ew", pady=(0, 8))

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
        seek_row.grid(row=9, column=0, sticky="ew", pady=(0, 4))
        seek_row.columnconfigure(0, weight=1)

        self._seek_scale = ttk.Scale(
            seek_row, from_=0, to=1, orient="horizontal", command=self._on_seek_drag
        )
        self._seek_scale.grid(row=0, column=0, sticky="ew")
        self._seek_scale.state(["disabled"])
        self._seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
        self._seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        time_volume_row = ttk.Frame(parent, style="App.TFrame")
        time_volume_row.grid(row=10, column=0, sticky="ew", pady=(0, 8))

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
        self._playback_status.grid(row=11, column=0, sticky="w")

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
        for combo in (self._provider_combo, self._language_combo, self._gender_combo, self._preset_combo):
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
            self._tts_manager.preview_voice(
                voice.id, preview_path,
                speed=self._current_settings.rate,
                pitch_hz=self._current_settings.pitch_hz,
                volume_percent=self._current_settings.volume_percent,
            ),
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
    # Generation (plain, single text box -- unchanged behavior)
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

        try:
            validate_preset(self._current_settings)
        except ConfigurationError as exc:
            self._generation_status.configure(text=str(exc), style="Error.TLabel")
            return

        voice = self._selected_voice

        # Release any lock on the currently-loaded (about to be replaced)
        # file BEFORE we start generating -- this is what makes it safe
        # to delete the old temp file once the new one lands.
        self._audio_player.stop()
        self._set_player_controls_enabled(False)

        output_path = self._config.generated_audio_dir / safe_filename(voice.id, "mp3")

        self._set_busy(True)
        self._progress.configure(mode="indeterminate", value=0)
        self._progress.start(12)
        self._generation_status.configure(text="Generating speech...", style="Muted.TLabel")
        self._playback_status.configure(text="Generating...", style="Muted.TLabel")
        self._on_status(f"Generating speech with {voice.name}...")

        self._bridge.run_coroutine(
            self._tts_manager.generate(
                text, voice.id, output_path,
                speed=self._current_settings.rate,
                pitch_hz=self._current_settings.pitch_hz,
                volume_percent=self._current_settings.volume_percent,
            ),
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

        self._save_name_hint = None
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
    # Phase 5: FFmpeg detection
    # ------------------------------------------------------------------

    def _detect_ffmpeg(self) -> None:
        if self._narration_running:
            return
        self._ffmpeg_status_label.configure(text="FFmpeg: checking...", style="Muted.TLabel")
        self._bridge.run_coroutine(
            self._ffmpeg.detect_async(),
            on_success=self._on_ffmpeg_detected,
            on_error=self._on_ffmpeg_detect_error,
        )

    def _on_ffmpeg_detected(self, status: FFmpegStatus) -> None:
        if status.available:
            self._ffmpeg_status_label.configure(text=f"FFmpeg: {status.message}", style="Success.TLabel")
        else:
            self._ffmpeg_status_label.configure(text=f"FFmpeg: {status.message}", style="Error.TLabel")
        self._refresh_narration_buttons()

    def _on_ffmpeg_detect_error(self, error: Exception) -> None:
        self._ffmpeg_status_label.configure(text=f"FFmpeg check failed: {error}", style="Error.TLabel")
        logger.error("FFmpeg detection failed: %s", error)
        self._refresh_narration_buttons()

    def _on_set_ffmpeg_path(self) -> None:
        path = filedialog.askopenfilename(
            title="Select ffmpeg.exe",
            filetypes=[("FFmpeg executable", "ffmpeg.exe ffmpeg"), ("All Files", "*.*")],
        )
        if not path:
            return
        self._ffmpeg.set_configured_path(path)
        self._detect_ffmpeg()

    def _ffmpeg_ready(self) -> bool:
        status = self._ffmpeg.status
        return status is not None and status.available

    # ------------------------------------------------------------------
    # Phase 5: narration (selected scene / full narration)
    # ------------------------------------------------------------------

    def _set_generation_message(self, text: str, style: str = "Muted.TLabel") -> None:
        self._generation_status.configure(text=text, style=style)

    def _on_generate_scene_click(self) -> None:
        if self._script_source is None:
            self._set_generation_message("The Script page is not connected.", "Error.TLabel")
            return
        scene = self._script_source.get_selected_scene()
        if scene is None:
            self._set_generation_message("Select a scene on the Script page first.", "Error.TLabel")
            return
        if not scene.text.strip():
            self._set_generation_message(f"'{scene.title}' has no text to narrate.", "Error.TLabel")
            return
        self._start_narration([scene], label=scene.title)

    def _on_generate_full_click(self) -> None:
        if self._script_source is None:
            self._set_generation_message("The Script page is not connected.", "Error.TLabel")
            return
        scenes = [s for s in self._script_source.get_scenes() if s.text.strip()]
        if not scenes:
            self._set_generation_message("The project has no scene text to narrate.", "Error.TLabel")
            return
        self._start_narration(scenes, label="Full narration")

    def _start_narration(self, scenes: List[Scene], label: str) -> None:
        if self._busy or self._narration_running:
            return
        if not self._ffmpeg_ready():
            message = self._ffmpeg.status.message if self._ffmpeg.status else "FFmpeg has not been checked yet."
            self._set_generation_message(message, "Error.TLabel")
            return

        default_voice_id = self._selected_voice.id if self._selected_voice else None
        try:
            requests: List[SceneRequest] = [
                build_scene_request(
                    scene, scene_index=scene.order + 1,
                    default_voice_id=default_voice_id, settings=self._current_settings,
                )
                for scene in scenes
            ]
        except ConfigurationError as exc:
            self._set_generation_message(str(exc), "Error.TLabel")
            return

        project_name = self._script_source.get_project_name() if self._script_source else "narration"
        base = f"{project_name} - {label}" if len(scenes) == 1 else f"{project_name} - narration"
        self._save_name_hint = _UNSAFE_NAME_CHARS.sub("", base).strip(" .") + ".mp3"

        # Release the old file BEFORE generating, as plain Generate does, so
        # it can be replaced/deleted safely afterwards.
        self._audio_player.stop()
        self._set_player_controls_enabled(False)

        self._cancel_token = CancelToken()
        self._narration_running = True
        self._set_busy(True)
        self._progress.stop()
        self._progress.configure(mode="determinate", maximum=100, value=0)
        self._set_generation_message(f"Preparing {label}...")
        self._playback_status.configure(text="Generating...", style="Muted.TLabel")
        self._on_status(f"Generating narration: {label}")

        self._bridge.run_coroutine(
            self._narration_job.run(
                requests,
                output_dir=self._config.generated_audio_dir,
                basename=base,
                cancel=self._cancel_token,
                on_progress=self._progress_from_worker,
            ),
            on_success=self._on_narration_success,
            on_error=self._on_narration_error,
        )

    def _progress_from_worker(self, event: ProgressEvent) -> None:
        # Called from background threads: only queue; never touch Tk here.
        self._bridge.dispatch(self._apply_progress, event)

    def _apply_progress(self, event: ProgressEvent) -> None:
        if not self._narration_running:
            return
        self._progress.configure(value=event.fraction * 100)
        self._set_generation_message(f"{event.message}  ({int(event.fraction * 100)}%)")

    def _on_cancel_click(self) -> None:
        if self._cancel_token is None or self._cancel_token.cancelled:
            return
        self._cancel_token.cancel()
        self._cancel_btn.configure(state="disabled")
        self._set_generation_message("Cancelling... finished chunks are kept.")

    def _finish_narration(self) -> None:
        self._narration_running = False
        self._cancel_token = None
        self._progress.configure(mode="determinate", value=0)
        self._set_busy(False)

    def _on_narration_success(self, result: NarrationResult) -> None:
        self._finish_narration()
        self._discard_narration_wav(keep=result.wav_path)

        try:
            duration = self._audio_player.load(result.mp3_path)
        except AudioProcessingError as exc:
            logger.warning("Narration saved but could not be loaded for playback: %s", exc)
            self._session.adopt_new_generation(result.mp3_path)
            self._narration_mp3, self._narration_wav = result.mp3_path, result.wav_path
            self._set_generation_message(
                f"Narration generated, but in-app playback is unavailable ({exc}). You can still use Save As.",
                "Error.TLabel",
            )
            self._set_player_controls_enabled(False)
            self._save_as_btn.configure(state="normal")
            return

        self._session.adopt_new_generation(result.mp3_path)
        self._narration_mp3, self._narration_wav = result.mp3_path, result.wav_path
        self._seek_scale.configure(to=max(duration, 0.1))
        self._seek_scale.set(0)
        self._set_player_controls_enabled(True)

        summary = (
            f"Narration ready: {_format_time(result.duration_seconds)}, {result.chunk_count} chunks "
            f"({result.cached_chunks} cached, {result.synthesized_chunks} generated). Not yet saved."
        )
        if result.warnings:
            summary += "\nNote: " + " ".join(result.warnings)
        self._set_generation_message(summary, "Success.TLabel")
        self._refresh_export_wav_state()
        self._on_status("Narration generated.")
        logger.info("Narration generated: %s (%.1fs)", result.mp3_path, result.duration_seconds)

    def _on_narration_error(self, error: Exception) -> None:
        self._finish_narration()
        # The previously loaded audio (if any) is still valid: re-enable it.
        current = self._session.current_path
        self._set_player_controls_enabled(current is not None and current.exists())
        self._playback_status.configure(text="Ready", style="Muted.TLabel")

        if isinstance(error, GenerationCancelled):
            self._set_generation_message(str(error), "Muted.TLabel")
            self._on_status("Narration cancelled.")
            return

        if isinstance(error, (NarrationError, FFmpegError, TTSProviderError, ConfigurationError, AudioProcessingError)):
            message = str(error)
        else:
            message = f"Unexpected error: {error}"
        self._set_generation_message(f"Narration failed: {message}", "Error.TLabel")
        self._on_status("Narration failed.")
        logger.error("Narration failed: %s", error)
        if isinstance(error, FFmpegError):
            self._detect_ffmpeg()

    def _refresh_narration_buttons(self) -> None:
        can_start = self._ffmpeg_ready() and not self._busy and not self._narration_running
        state = "normal" if can_start else "disabled"
        self._scene_narration_btn.configure(state=state)
        self._full_narration_btn.configure(state=state)
        cancelable = (
            self._narration_running
            and self._cancel_token is not None
            and not self._cancel_token.cancelled
        )
        self._cancel_btn.configure(state="normal" if cancelable else "disabled")
        tools_state = "disabled" if self._narration_running else "normal"
        self._ffmpeg_check_btn.configure(state=tools_state)
        self._ffmpeg_path_btn.configure(state=tools_state)
        self._refresh_export_wav_state()

    def _refresh_export_wav_state(self) -> None:
        """Export WAV is only offered while the loaded audio IS the narration
        the WAV belongs to (plain Generate replaces the current audio)."""
        wav = self._narration_wav
        available = (
            wav is not None
            and wav.exists()
            and self._narration_mp3 is not None
            and self._session.current_path == self._narration_mp3
            and not self._narration_running
        )
        self._export_wav_btn.configure(state="normal" if available else "disabled")

    def _discard_narration_wav(self, keep: Optional[Path] = None) -> None:
        wav = self._narration_wav
        if wav is not None and wav != keep:
            try:
                wav.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not remove old narration WAV %s: %s", wav, exc)
        if keep is None:
            self._narration_wav = None

    def _on_export_wav_click(self) -> None:
        wav = self._narration_wav
        if wav is None or not wav.exists():
            self._set_generation_message("There is no narration WAV to export.", "Error.TLabel")
            return
        suggested = (Path(self._save_name_hint).stem if self._save_name_hint else "narration") + ".wav"
        destination = filedialog.asksaveasfilename(
            title="Export Narration WAV",
            defaultextension=".wav",
            filetypes=[("WAV Audio", "*.wav")],
            initialdir=str(self._config.output_dir),
            initialfile=suggested,
        )
        if not destination:
            self._set_generation_message("Export cancelled.")
            return

        self._export_wav_btn.configure(state="disabled")
        self._set_generation_message("Exporting WAV...")
        target = Path(destination)

        def copy_file() -> Path:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wav, target)
            if not target.exists() or target.stat().st_size != wav.stat().st_size:
                raise OSError("the exported file could not be verified after copying")
            return target

        self._bridge.run_coroutine(
            asyncio.to_thread(copy_file),
            on_success=lambda path: self._set_generation_message(f"WAV saved to: {path}", "Success.TLabel"),
            on_error=lambda exc: self._set_generation_message(f"WAV export failed: {exc}", "Error.TLabel"),
        )

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

        suggested_name = self._save_name_hint or (
            f"{self._selected_voice.id}.mp3" if self._selected_voice else "narration.mp3"
        )
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
        self._refresh_export_wav_state()
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
        self._refresh_narration_buttons()

    # ------------------------------------------------------------------
    # Lifecycle hooks called by MainWindow
    # ------------------------------------------------------------------

    def confirm_close(self) -> bool:
        """Return False to veto closing the application."""
        if self._narration_running:
            if not messagebox.askyesno(
                "Narration In Progress",
                "A narration is still being generated. Finished chunks are saved and "
                f"can be resumed later.\n\nClose {APP_NAME} anyway?",
            ):
                return False
        if self._session.current_path is not None and not self._session.is_saved:
            return messagebox.askyesno(
                "Unsaved Audio",
                "You have generated audio that hasn't been saved with "
                f"Save As.\n\nClose {APP_NAME} anyway?",
            )
        return True

    def shutdown(self) -> None:
        if self._ui_update_job is not None:
            try:
                self.after_cancel(self._ui_update_job)
            except Exception:
                pass
            self._ui_update_job = None
        if self._cancel_token is not None:
            self._cancel_token.cancel()
        self._audio_player.shutdown()
        self._session.cleanup()
        self._discard_narration_wav()