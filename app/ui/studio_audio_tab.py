from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import List, Optional, Tuple

from app.audio.player import AudioPlayer, PlaybackState
from app.core.constants import AUDIO_EXTENSIONS
from app.core.exceptions import AudioProcessingError, MediaError
from app.core.logger import get_logger
from app.studio.models import MusicTrack
from app.studio.previews import make_waveform, render_mix_preview
from app.ui.studio_context import StudioContext, fmt_seconds, short_name

logger = get_logger("ui.studio.audio")

_WAVE_W, _WAVE_H = 760, 90
_NARRATION = "Current narration"
_MIX_PREVIEW = "Mix preview (first 30 s)"


class AudioTab(ttk.Frame):
    """Background music, volumes, fades, trimming, waveform + playback and
    the 30-second mix preview. All FFmpeg work runs on worker threads."""

    def __init__(self, master: tk.Widget, ctx: StudioContext) -> None:
        super().__init__(master, style="App.TFrame")
        self._ctx = ctx
        self._player = AudioPlayer()
        self._sources: List[Tuple[str, Optional[Path]]] = []
        self._source_path: Optional[Path] = None
        self._wave_image: Optional[tk.PhotoImage] = None
        self._mix_preview_path: Optional[Path] = None
        self._seeking = False
        self._loading = False
        self._tick_job: Optional[str] = None
        self._build()
        self._tick()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        ctx = self._ctx

        top = ttk.Frame(self, style="App.TFrame")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        ttk.Label(top, text="Narration volume:", style="Muted.TLabel").pack(side="left")
        self._nvol_label = ttk.Label(top, text="100%", style="Muted.TLabel", width=6)
        self._nvol = ttk.Scale(top, from_=0, to=200, orient="horizontal", length=200, command=self._on_nvol)
        self._nvol.pack(side="left", padx=8)
        self._nvol_label.pack(side="left")
        self._limiter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Prevent clipping (limiter)", variable=self._limiter_var,
                        command=self._on_limiter).pack(side="left", padx=(24, 0))

        ttk.Label(self, text="Background music", style="SectionTitle.TLabel").grid(
            row=1, column=0, sticky="w", padx=16, pady=(8, 4))
        tree_row = ttk.Frame(self, style="App.TFrame")
        tree_row.grid(row=2, column=0, sticky="ew", padx=16)
        tree_row.columnconfigure(0, weight=1)
        cols = ("on", "file", "vol", "fade", "offset", "trim", "loop")
        self._tree = ttk.Treeview(tree_row, columns=cols, show="headings", height=4, style="Scene.Treeview",
                                  selectmode="browse")
        for col, text, width in (("on", "On", 36), ("file", "File", 240), ("vol", "Volume", 64),
                                 ("fade", "Fade in/out", 84), ("offset", "Starts at", 70),
                                 ("trim", "Trim", 110), ("loop", "Loop", 48)):
            self._tree.heading(col, text=text)
            self._tree.column(col, width=width, anchor="w" if col == "file" else "center")
        self._tree.grid(row=0, column=0, sticky="ew")
        self._tree.bind("<<TreeviewSelect>>", lambda _e: self._on_track_selected())
        buttons = ttk.Frame(tree_row, style="App.TFrame")
        buttons.grid(row=0, column=1, sticky="n", padx=(8, 0))
        for text, cmd in (("Add Music...", self._on_add), ("Edit...", self._on_edit), ("Remove", self._on_remove)):
            ttk.Button(buttons, text=text, style="Secondary.TButton", command=cmd).pack(fill="x", pady=2)

        ttk.Label(self, text="Audio editor", style="SectionTitle.TLabel").grid(
            row=3, column=0, sticky="w", padx=16, pady=(12, 4))
        src_row = ttk.Frame(self, style="App.TFrame")
        src_row.grid(row=4, column=0, sticky="ew", padx=16)
        ttk.Label(src_row, text="Source:", style="Muted.TLabel").pack(side="left")
        self._source_var = tk.StringVar()
        self._source_combo = ttk.Combobox(src_row, textvariable=self._source_var, state="readonly",
                                          style="App.TCombobox", width=44)
        self._source_combo.pack(side="left", padx=8)
        self._source_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_selected_source())
        self._wave_status = ttk.Label(src_row, text="", style="Muted.TLabel")
        self._wave_status.pack(side="left", padx=8)

        self._canvas = tk.Canvas(self, width=_WAVE_W, height=_WAVE_H, highlightthickness=1,
                                 background=ctx.palette["field_bg"], highlightbackground=ctx.palette["border"])
        self._canvas.grid(row=5, column=0, padx=16, pady=(6, 2), sticky="w")
        self._canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        transport = ttk.Frame(self, style="App.TFrame")
        transport.grid(row=6, column=0, sticky="ew", padx=16, pady=(2, 0))
        self._play_btn = ttk.Button(transport, text="\u25b6 Play", style="Primary.TButton", command=self._on_play,
                                    state="disabled")
        self._play_btn.pack(side="left")
        self._stop_btn = ttk.Button(transport, text="\u25a0 Stop", style="Secondary.TButton", command=self._on_stop,
                                    state="disabled")
        self._stop_btn.pack(side="left", padx=(6, 0))
        self._time_label = ttk.Label(transport, text="00:00 / 00:00", style="Muted.TLabel")
        self._time_label.pack(side="left", padx=12)
        self._trim_start_btn = ttk.Button(transport, text="Set Start Here", style="Secondary.TButton",
                                          command=lambda: self._trim_here("start"), state="disabled")
        self._trim_start_btn.pack(side="left", padx=(12, 0))
        self._trim_end_btn = ttk.Button(transport, text="Set End Here", style="Secondary.TButton",
                                        command=lambda: self._trim_here("end"), state="disabled")
        self._trim_end_btn.pack(side="left", padx=(6, 0))
        self._trim_clear_btn = ttk.Button(transport, text="Clear Trim", style="Secondary.TButton",
                                          command=lambda: self._trim_here("clear"), state="disabled")
        self._trim_clear_btn.pack(side="left", padx=(6, 0))

        self._seek = ttk.Scale(self, from_=0, to=1, orient="horizontal", command=self._on_seek_drag)
        self._seek.grid(row=7, column=0, sticky="ew", padx=16, pady=(4, 0))
        self._seek.bind("<ButtonPress-1>", lambda _e: setattr(self, "_seeking", True))
        self._seek.bind("<ButtonRelease-1>", self._on_seek_release)

        bottom = ttk.Frame(self, style="App.TFrame")
        bottom.grid(row=8, column=0, sticky="ew", padx=16, pady=(10, 4))
        self._preview_btn = ttk.Button(bottom, text="Preview Mix (30 s)", style="Primary.TButton",
                                       command=self._on_preview_mix)
        self._preview_btn.pack(side="left")
        ttk.Button(bottom, text="Export Final Audio (MP3/WAV)...", style="Secondary.TButton",
                   command=lambda: ctx.export_audio()).pack(side="left", padx=8)
        self._status = ttk.Label(self, text="", style="Muted.TLabel", wraplength=900, justify="left")
        self._status.grid(row=9, column=0, sticky="w", padx=16)

    # ------------------------------------------------------------------ state <-> widgets

    def refresh(self) -> None:
        audio = self._ctx.state.audio
        self._loading = True
        self._nvol.set(audio.narration_volume_percent)
        self._nvol_label.configure(text=f"{audio.narration_volume_percent}%")
        self._limiter_var.set(audio.limiter)
        self._loading = False
        self._fill_tree()
        self._rebuild_sources()

    def _fill_tree(self, select_id: Optional[str] = None) -> None:
        self._tree.delete(*self._tree.get_children())
        for t in self._ctx.state.audio.tracks:
            trim = "-" if t.trim_start_s == 0 and t.trim_end_s is None else \
                f"{t.trim_start_s:g}s - {('end' if t.trim_end_s is None else f'{t.trim_end_s:g}s')}"
            self._tree.insert("", "end", iid=t.id, values=(
                "\u2713" if t.enabled else "", short_name(t.path), f"{t.volume_percent}%",
                f"{t.fade_in_s:g}s / {t.fade_out_s:g}s", f"{t.offset_s:g}s", trim, "yes" if t.loop else "no"))
        if select_id and self._tree.exists(select_id):
            self._tree.selection_set(select_id)

    def _selected_track(self) -> Optional[MusicTrack]:
        sel = self._tree.selection()
        return next((t for t in self._ctx.state.audio.tracks if sel and t.id == sel[0]), None)

    def _on_nvol(self, value: str) -> None:
        volume = int(round(float(value)))
        self._nvol_label.configure(text=f"{volume}%")
        if not self._loading:
            self._ctx.state.audio.narration_volume_percent = volume
            self._ctx.commit()

    def _on_limiter(self) -> None:
        self._ctx.state.audio.limiter = bool(self._limiter_var.get())
        self._ctx.commit()

    # ------------------------------------------------------------------ track management

    def _on_add(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Add background music",
            filetypes=[("Audio", " ".join(f"*{e}" for e in AUDIO_EXTENSIONS)), ("All files", "*.*")])
        if not paths:
            return
        self._set_status("Checking audio files...")

        def check(files):
            ok, bad = [], []
            for f in files:
                try:
                    info = self._ctx.ffmpeg.probe(Path(f))
                    (ok if info.has_audio and info.duration_s else bad).append((f, info.duration_s))
                except MediaError as exc:
                    bad.append((f, str(exc)))
            return ok, bad

        self._ctx.run_bg(check, list(paths), on_success=self._added, on_error=lambda e: self._set_status(f"Could not read the files: {e}"))

    def _added(self, result) -> None:
        ok, bad = result
        last = None
        for path, _duration in ok:
            track = MusicTrack(path=path)
            self._ctx.state.audio.tracks.append(track)
            last = track.id
        if ok:
            self._ctx.commit()
        self._fill_tree(last)
        self._rebuild_sources()
        message = f"Added {len(ok)} track(s)."
        if bad:
            message += " Skipped (not readable audio): " + ", ".join(short_name(p) for p, _ in bad)
        self._set_status(message)

    def _on_remove(self) -> None:
        track = self._selected_track()
        if track is None:
            return
        self._ctx.state.audio.tracks.remove(track)
        self._ctx.commit()
        self._fill_tree()
        self._rebuild_sources()

    def _on_edit(self) -> None:
        track = self._selected_track()
        if track is None:
            self._set_status("Select a track first.")
            return
        dialog = TrackDialog(self, track)
        self.wait_window(dialog)
        if dialog.result:
            self._ctx.commit()
            self._fill_tree(track.id)

    def _on_track_selected(self) -> None:
        track = self._selected_track()
        if track is not None:
            label = self._label_for(track)
            if label in self._source_combo["values"]:
                self._source_var.set(label)
                self._load_selected_source()

    # ------------------------------------------------------------------ audio editor

    @staticmethod
    def _label_for(track: MusicTrack) -> str:
        return f"Music: {short_name(track.path)} [{track.id}]"

    def _rebuild_sources(self) -> None:
        self._sources = [(_NARRATION, None)]
        for t in self._ctx.state.audio.tracks:
            self._sources.append((self._label_for(t), Path(t.path)))
        if self._mix_preview_path is not None:
            self._sources.append((_MIX_PREVIEW, self._mix_preview_path))
        labels = [label for label, _ in self._sources]
        self._source_combo.configure(values=labels)
        if self._source_var.get() not in labels:
            self._source_var.set(labels[0])

    def _resolve_source(self) -> Optional[Path]:
        label = self._source_var.get()
        if label == _NARRATION:
            return self._ctx.voice.current_narration_wav()
        return next((p for l, p in self._sources if l == label), None)

    def _load_selected_source(self) -> None:
        self._player.stop()
        self._canvas.delete("all")
        self._wave_image = None
        path = self._resolve_source()
        self._source_path = None
        for btn in (self._play_btn, self._stop_btn, self._trim_start_btn, self._trim_end_btn, self._trim_clear_btn):
            btn.configure(state="disabled")
        if path is None or not path.exists():
            self._wave_status.configure(text="No narration yet - generate it on the Voice & Narration tab."
                                        if self._source_var.get() == _NARRATION else "File not found.")
            return
        try:
            duration = self._player.load(path)
        except AudioProcessingError as exc:
            self._wave_status.configure(text=f"Cannot play this file: {exc}")
            return
        self._source_path = path
        self._seek.configure(to=max(duration, 0.1))
        self._seek.set(0)
        self._play_btn.configure(state="normal")
        self._stop_btn.configure(state="normal")
        is_music = self._source_var.get().startswith("Music:")
        for btn in (self._trim_start_btn, self._trim_end_btn, self._trim_clear_btn):
            btn.configure(state="normal" if is_music else "disabled")
        self._wave_status.configure(text="Drawing waveform...")
        self._ctx.run_bg(make_waveform, self._ctx.ffmpeg, self._ctx.video_cache, path, _WAVE_W, _WAVE_H,
                         on_success=lambda png, p=path: self._show_wave(png, p),
                         on_error=lambda e: self._wave_status.configure(text=f"No waveform: {e}"))

    def _show_wave(self, png: Path, for_path: Path) -> None:
        if for_path != self._source_path:   # user switched source while it was drawing
            return
        try:
            self._wave_image = tk.PhotoImage(file=str(png))
        except tk.TclError as exc:
            self._wave_status.configure(text=f"No waveform: {exc}")
            return
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, image=self._wave_image, anchor="nw", tags="wave")
        self._canvas.create_line(0, 0, 0, _WAVE_H, fill=self._ctx.palette["accent"], width=2, tags="playhead")
        self._wave_status.configure(text="")

    def _duration(self) -> float:
        return self._player.get_status().duration_seconds

    def _on_play(self) -> None:
        self._ctx.voice.stop_playback()
        status = self._player.get_status()
        try:
            if status.state == PlaybackState.PLAYING:
                self._player.pause()
            elif status.state == PlaybackState.PAUSED:
                self._player.resume()
            else:
                self._player.play(0.0)
        except AudioProcessingError as exc:
            self._set_status(str(exc))

    def _on_stop(self) -> None:
        self._player.stop()

    def _on_seek_drag(self, value: str) -> None:
        if self._seeking:
            self._time_label.configure(text=f"{fmt_seconds(float(value))} / {fmt_seconds(self._duration())}")

    def _on_seek_release(self, _e=None) -> None:
        self._seeking = False
        if self._source_path is not None:
            try:
                self._player.seek(self._seek.get())
            except AudioProcessingError as exc:
                self._set_status(str(exc))

    def _on_canvas_press(self, _e) -> None:
        self._seeking = True

    def _on_canvas_release(self, event) -> None:
        self._seeking = False
        duration = self._duration()
        if self._source_path is not None and duration > 0:
            try:
                self._player.seek(max(0.0, min(duration, event.x / _WAVE_W * duration)))
            except AudioProcessingError as exc:
                self._set_status(str(exc))

    def _trim_here(self, which: str) -> None:
        track = self._selected_track()
        if track is None:
            return
        position = round(self._player.get_status().position_seconds, 1)
        if which == "clear":
            track.trim_start_s, track.trim_end_s = 0.0, None
        elif which == "start":
            if track.trim_end_s is not None and position >= track.trim_end_s:
                self._set_status("The start must be before the end.")
                return
            track.trim_start_s = position
        else:
            if position <= track.trim_start_s:
                self._set_status("The end must be after the start.")
                return
            track.trim_end_s = position
        self._ctx.commit()
        self._fill_tree(track.id)
        self._set_status(f"Trim for {short_name(track.path)}: {track.trim_start_s:g}s - "
                         f"{'end' if track.trim_end_s is None else f'{track.trim_end_s:g}s'} (applied when mixing).")

    def _tick(self) -> None:
        try:
            status = self._player.get_status()
            if not self._seeking and self._source_path is not None:
                self._seek.set(status.position_seconds)
                self._time_label.configure(
                    text=f"{fmt_seconds(status.position_seconds)} / {fmt_seconds(status.duration_seconds)}")
            self._play_btn.configure(text="\u23f8 Pause" if status.state == PlaybackState.PLAYING else "\u25b6 Play")
            if status.duration_seconds > 0:
                x = status.position_seconds / status.duration_seconds * _WAVE_W
                self._canvas.coords("playhead", x, 0, x, _WAVE_H)
        except tk.TclError:
            return
        self._tick_job = self.after(200, self._tick)

    # ------------------------------------------------------------------ mix preview

    def _on_preview_mix(self) -> None:
        narration = self._ctx.voice.current_narration_wav()
        if narration is None:
            self._set_status("Generate narration first (Voice & Narration tab), then preview the mix.")
            return
        self._player.stop()
        self._preview_btn.configure(state="disabled")
        self._set_status("Rendering the first 30 seconds of the mix...")
        dest = self._ctx.config.temp_dir / "mix_preview.wav"
        audio = self._ctx.state.audio

        def work():
            from app.audio.assembler import wav_duration_seconds
            return render_mix_preview(self._ctx.ffmpeg, narration, wav_duration_seconds(narration), audio, dest, 30.0)

        self._ctx.run_bg(work, on_success=self._preview_ready, on_error=self._preview_failed)

    def _preview_ready(self, path: Path) -> None:
        self._preview_btn.configure(state="normal")
        self._mix_preview_path = Path(path)
        self._rebuild_sources()
        self._source_var.set(_MIX_PREVIEW)
        self._load_selected_source()
        self._set_status("Mix preview ready - press Play.")

    def _preview_failed(self, error: Exception) -> None:
        self._preview_btn.configure(state="normal")
        self._set_status(f"Mix preview failed: {error}")

    # ------------------------------------------------------------------ misc

    def _set_status(self, text: str) -> None:
        self._status.configure(text=text)

    def apply_theme(self, palette: dict) -> None:
        self._canvas.configure(background=palette["field_bg"], highlightbackground=palette["border"])

    def shutdown(self) -> None:
        if self._tick_job is not None:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
        self._player.shutdown()
        try:
            (self._ctx.config.temp_dir / "mix_preview.wav").unlink(missing_ok=True)
        except OSError:
            pass


class TrackDialog(tk.Toplevel):
    """Edit one music track. `result` is True when the user pressed OK."""

    FIELDS = (
        ("volume_percent", "Volume (0-200 %)", 0, 200, 1),
        ("fade_in_s", "Fade in (s)", 0, 600, 0.5),
        ("fade_out_s", "Fade out (s)", 0, 600, 0.5),
        ("offset_s", "Starts at (s on timeline)", 0, 86400, 1),
        ("trim_start_s", "Trim start (s)", 0, 86400, 1),
    )

    def __init__(self, master, track: MusicTrack) -> None:
        super().__init__(master)
        self.title(f"Edit music - {short_name(track.path)}")
        self.transient(master.winfo_toplevel())
        self.resizable(False, False)
        self.result = False
        self._track = track
        self._vars = {}
        body = ttk.Frame(self, padding=14)
        body.grid(sticky="nsew")
        for row, (name, label, lo, hi, step) in enumerate(self.FIELDS):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=f"{getattr(track, name):g}")
            ttk.Spinbox(body, from_=lo, to=hi, increment=step, textvariable=var, width=10).grid(row=row, column=1, padx=8)
            self._vars[name] = var
        row = len(self.FIELDS)
        ttk.Label(body, text="Trim end (s, blank = end of file)").grid(row=row, column=0, sticky="w", pady=3)
        self._end = tk.StringVar(value="" if track.trim_end_s is None else f"{track.trim_end_s:g}")
        ttk.Entry(body, textvariable=self._end, width=12).grid(row=row, column=1, padx=8)
        self._loop = tk.BooleanVar(value=track.loop)
        self._enabled = tk.BooleanVar(value=track.enabled)
        ttk.Checkbutton(body, text="Loop to fill the narration", variable=self._loop).grid(row=row + 1, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(body, text="Use this track", variable=self._enabled).grid(row=row + 2, column=0, columnspan=2, sticky="w")
        self._error = ttk.Label(body, text="", foreground="#c62828")
        self._error.grid(row=row + 3, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=row + 4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _ok(self) -> None:
        try:
            values = {name: float(var.get()) for name, var in self._vars.items()}
            end_text = self._end.get().strip()
            end = float(end_text) if end_text else None
        except ValueError:
            self._error.configure(text="Please enter numbers only.")
            return
        if any(v < 0 for v in values.values()) or not 0 <= values["volume_percent"] <= 200:
            self._error.configure(text="Volume must be 0-200 and times cannot be negative.")
            return
        if end is not None and end <= values["trim_start_s"]:
            self._error.configure(text="Trim end must be after trim start.")
            return
        t = self._track
        t.volume_percent = int(values["volume_percent"])
        t.fade_in_s, t.fade_out_s = values["fade_in_s"], values["fade_out_s"]
        t.offset_s, t.trim_start_s, t.trim_end_s = values["offset_s"], values["trim_start_s"], end
        t.loop, t.enabled = bool(self._loop.get()), bool(self._enabled.get())
        self.result = True
        self.destroy()