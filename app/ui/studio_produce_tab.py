from __future__ import annotations

import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from app.core.exceptions import (
    ConfigurationError,
    FFmpegError,
    GenerationCancelled,
    MediaError,
    NarrationError,
    ProductionError,
    TTSProviderError,
)
from app.core.logger import get_logger
from app.studio.validation import ERROR, INFO, WARNING, ValidationIssue, has_errors, validate_production
from app.ui.studio_context import StudioContext, fmt_seconds
from app.workers.cancel import CancelToken
from app.workers.production import (
    ProductionJob,
    ProductionOptions,
    ProductionProgress,
    ProductionResult,
    SceneInfo,
)

logger = get_logger("ui.studio.produce")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ProduceTab(ttk.Frame):
    """The guided end-to-end workflow: validate -> narrate (cached) -> mix ->
    render -> export. One background job, one progress bar, one Cancel."""

    def __init__(self, master: tk.Widget, ctx: StudioContext) -> None:
        super().__init__(master, style="App.TFrame")
        self._ctx = ctx
        self._token: Optional[CancelToken] = None
        self.running = False
        self._last_dir: Optional[Path] = None
        self._video_var = tk.BooleanVar(value=True)
        self._audio_var = tk.BooleanVar(value=False)
        self._format_var = tk.StringVar(value="mp3")
        self._folder_var = tk.StringVar(value=str(ctx.config.output_dir))
        self._name_var = tk.StringVar(value="")
        self._confirmed_overwrite = False
        self._build()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Produce", style="SectionTitle.TLabel").grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        ttk.Label(self, text="Script -> narration -> music mix -> scene video -> final MP4. Narration and scene video that "
                             "are still valid are reused, so only what changed is generated again.",
                  style="Muted.TLabel", wraplength=860, justify="left").grid(row=1, column=0, sticky="w", padx=16)

        opts = ttk.Frame(self, style="App.TFrame")
        opts.grid(row=2, column=0, sticky="ew", padx=16, pady=(10, 4))
        ttk.Checkbutton(opts, text="Render video (MP4, H.264 + AAC)", variable=self._video_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(opts, text="Export audio", variable=self._audio_var).grid(row=0, column=1, sticky="w", padx=(20, 4))
        ttk.Combobox(opts, textvariable=self._format_var, values=["mp3", "wav"], state="readonly",
                     style="App.TCombobox", width=6).grid(row=0, column=2, sticky="w")
        ttk.Label(opts, text="Folder:", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(opts, textvariable=self._folder_var, width=62).grid(row=1, column=1, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(opts, text="Browse...", style="Secondary.TButton", command=self._browse).grid(row=1, column=3, padx=6, pady=(8, 0))
        ttk.Label(opts, text="File name:", style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(opts, textvariable=self._name_var, width=40).grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Label(opts, text="(without extension; existing files are never replaced without asking)",
                  style="Muted.TLabel").grid(row=2, column=3, sticky="w", padx=6, pady=(6, 0))

        ttk.Label(self, text="Checklist", style="SectionTitle.TLabel").grid(row=3, column=0, sticky="w", padx=16, pady=(10, 2))
        box = ttk.Frame(self, style="App.TFrame")
        box.grid(row=4, column=0, sticky="ew", padx=16)
        box.columnconfigure(0, weight=1)
        self._issues = ttk.Treeview(box, columns=("level", "msg"), show="headings", height=6, style="Scene.Treeview")
        self._issues.heading("level", text="")
        self._issues.heading("msg", text="Check")
        self._issues.column("level", width=70, anchor="center")
        self._issues.column("msg", width=760)
        self._issues.grid(row=0, column=0, sticky="ew")

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=5, column=0, sticky="ew", padx=16, pady=(10, 4))
        ttk.Button(actions, text="Check Project", style="Secondary.TButton", command=self._on_validate).pack(side="left")
        self._start_btn = ttk.Button(actions, text="Start Production", style="Primary.TButton", command=self._on_start)
        self._start_btn.pack(side="left", padx=8)
        self._cancel_btn = ttk.Button(actions, text="Cancel", style="Secondary.TButton", command=self._on_cancel, state="disabled")
        self._cancel_btn.pack(side="left")
        self._open_btn = ttk.Button(actions, text="Open Output Folder", style="Secondary.TButton", command=self._open_folder, state="disabled")
        self._open_btn.pack(side="left", padx=8)

        self._progress = ttk.Progressbar(self, mode="determinate", maximum=100, style="App.Horizontal.TProgressbar")
        self._progress.grid(row=6, column=0, sticky="ew", padx=16, pady=(6, 2))
        self._stage = ttk.Label(self, text="Ready", style="App.TLabel")
        self._stage.grid(row=7, column=0, sticky="w", padx=16)
        self._message = ttk.Label(self, text="", style="Muted.TLabel", wraplength=860, justify="left")
        self._message.grid(row=8, column=0, sticky="w", padx=16, pady=(0, 8))

    # ------------------------------------------------------------------ helpers

    def refresh(self) -> None:
        if not self._name_var.get().strip():
            self._name_var.set(self._safe_name(self._ctx.script.get_project_name()))

    @staticmethod
    def _safe_name(name: str) -> str:
        cleaned = _UNSAFE.sub("", name).strip(" .")
        return cleaned or "voxora-video"

    def _browse(self) -> None:
        folder = filedialog.askdirectory(title="Choose the output folder", initialdir=self._folder_var.get() or None)
        if folder:
            self._folder_var.set(folder)

    def _outputs(self):
        folder = Path(self._folder_var.get().strip() or self._ctx.config.output_dir)
        name = self._safe_name(self._name_var.get())
        video = folder / f"{name}.mp4" if self._video_var.get() else None
        audio = folder / f"{name}.{self._format_var.get()}" if self._audio_var.get() else None
        return folder, video, audio

    def _gather_issues(self) -> List[ValidationIssue]:
        scenes = self._ctx.scenes()
        voice = self._ctx.voice
        issues = validate_production(
            scenes, self._ctx.state,
            ffmpeg_ready=voice.ffmpeg_ready(), voice_selected=bool(voice.selected_voice_id()),
            render_video=self._video_var.get(), export_audio=self._audio_var.get(),
        )
        folder, _video, _audio = self._outputs()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".voxora_write_test"
            probe.write_text("x")
            probe.unlink()
        except OSError as exc:
            issues.append(ValidationIssue(ERROR, f"Cannot write to the output folder: {exc}"))
        if voice.is_busy() and not self.running:
            issues.append(ValidationIssue(ERROR, "Another generation is running on the Voice & Narration tab. Wait for it to finish."))
        return issues

    def _show_issues(self, issues: List[ValidationIssue]) -> None:
        self._issues.delete(*self._issues.get_children())
        if not issues:
            self._issues.insert("", "end", values=("OK", "Everything needed is in place."))
            return
        labels = {ERROR: "ERROR", WARNING: "Warning", INFO: "Note"}
        for issue in sorted(issues, key=lambda i: (i.severity != ERROR, i.severity != WARNING)):
            self._issues.insert("", "end", values=(labels.get(issue.severity, ""), issue.message))

    def _on_validate(self) -> None:
        issues = self._gather_issues()
        self._show_issues(issues)
        self._message.configure(text="Fix the errors above before producing." if has_errors(issues)
                                else "The project is ready to produce.")

    # ------------------------------------------------------------------ run

    def _on_start(self) -> None:
        if self.running:
            return
        issues = self._gather_issues()
        self._show_issues(issues)
        if has_errors(issues):
            self._message.configure(text="Fix the errors in the checklist first.")
            return
        warnings = [i for i in issues if i.severity == WARNING]
        if warnings and not messagebox.askyesno("Continue?", f"{len(warnings)} warning(s) in the checklist "
                                                              "(for example scenes without media become black screens).\n\nContinue anyway?"):
            return
        folder, video_path, audio_path = self._outputs()
        existing = [p for p in (video_path, audio_path) if p is not None and p.exists()]
        confirmed, self._confirmed_overwrite = self._confirmed_overwrite, False
        if existing and not confirmed and not messagebox.askyesno("Replace existing file?", "These files already exist:\n\n" +
                                                "\n".join(str(p) for p in existing) + "\n\nReplace them?"):
            return

        scenes = self._ctx.scenes()
        narrated = [s for s in scenes if s.text.strip()]
        try:
            requests = self._ctx.voice.build_scene_requests(narrated)
        except ConfigurationError as exc:
            self._message.configure(text=str(exc))
            return
        infos = [SceneInfo(s.id, s.title, s.text) for s in scenes]
        job = ProductionJob(self._ctx.voice.narration_job, self._ctx.ffmpeg, self._ctx.video_cache, self._ctx.config.temp_dir)
        options = ProductionOptions(
            render_video=self._video_var.get(), export_audio=self._audio_var.get(),
            video_output=video_path, audio_output=audio_path, audio_format=self._format_var.get(),
        )
        self._ctx.voice.stop_playback()
        self._last_dir = folder
        self._token = CancelToken()
        self.running = True
        self._ctx.voice.set_external_busy(True)
        self._set_running(True)
        self._progress.configure(value=0)
        self._stage.configure(text="Starting...")
        self._message.configure(text="")
        self._ctx.bridge.run_coroutine(
            job.run(requests, infos, self._ctx.state, options, basename=self._safe_name(self._name_var.get()),
                    cancel=self._token, on_progress=lambda p: self._ctx.bridge.dispatch(self._apply_progress, p)),
            on_success=self._on_done, on_error=self._on_failed,
        )

    def _apply_progress(self, progress: ProductionProgress) -> None:
        if not self.running:
            return
        self._progress.configure(value=progress.fraction * 100)
        self._stage.configure(text=f"{progress.stage} - {int(progress.fraction * 100)}%")
        self._message.configure(text=progress.message)

    def _on_cancel(self) -> None:
        if self._token is not None and not self._token.cancelled:
            self._token.cancel()
            self._cancel_btn.configure(state="disabled")
            self._message.configure(text="Cancelling... unfinished files are removed; finished narration and scene clips are kept.")

    def _finish(self) -> None:
        self.running = False
        self._token = None
        self._ctx.voice.set_external_busy(False)
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._start_btn.configure(state="disabled" if running else "normal")
        self._cancel_btn.configure(state="normal" if running else "disabled")

    def _on_done(self, result: ProductionResult) -> None:
        self._finish()
        for audio in result.narration.scene_audio:
            self._ctx.known_durations[audio.scene_id] = audio.duration_s
        self._progress.configure(value=100)
        self._stage.configure(text="Finished")
        lines = []
        if result.video_path:
            lines.append(f"Video: {result.video_path}")
        if result.audio_path:
            lines.append(f"Audio: {result.audio_path}")
        text = f"Length {fmt_seconds(result.duration_s)}."
        if result.video_path:
            text += f" Scene clips: {result.segments_rendered} rendered, {result.segments_cached} reused."
        if result.warnings:
            text += "\nNotes: " + " ".join(result.warnings)
        self._message.configure(text=text)
        self._open_btn.configure(state="normal")
        self._ctx.on_status("Production finished.")
        self._ctx.refresh_scenes()
        messagebox.showinfo("Production complete", "\n".join(lines) + f"\n\n{text}")

    def _on_failed(self, error: Exception) -> None:
        self._finish()
        self._progress.configure(value=0)
        if isinstance(error, GenerationCancelled):
            self._stage.configure(text="Cancelled")
            self._message.configure(text=str(error) if "saved" in str(error) else "Cancelled. No output file was created.")
            self._ctx.on_status("Production cancelled.")
            return
        known = (ProductionError, MediaError, FFmpegError, NarrationError, TTSProviderError, ConfigurationError)
        text = str(error) if isinstance(error, known) else f"Unexpected error: {error}"
        self._stage.configure(text="Failed")
        self._message.configure(text=text)
        self._ctx.on_status("Production failed.")
        logger.error("Production failed: %s", error)

    def _open_folder(self) -> None:
        folder = self._last_dir
        if folder is None or not folder.exists():
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(folder))  # type: ignore[attr-defined]  # Windows
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            self._message.configure(text=f"Could not open the folder: {exc}")

    # ------------------------------------------------------------------ audio-only shortcut

    def export_audio_dialog(self) -> None:
        """Called from the Audio tab: pick a file name, then run an audio-only production."""
        if self.running:
            return
        path = filedialog.asksaveasfilename(
            title="Export final audio", defaultextension=".mp3",
            filetypes=[("MP3 audio", "*.mp3"), ("WAV audio", "*.wav")],
            initialdir=self._folder_var.get() or None,
            initialfile=f"{self._safe_name(self._name_var.get() or self._ctx.script.get_project_name())}.mp3",
        )
        if not path:
            return
        target = Path(path)
        self._folder_var.set(str(target.parent))
        self._name_var.set(target.stem)
        self._format_var.set("wav" if target.suffix.lower() == ".wav" else "mp3")
        self._video_var.set(False)
        self._audio_var.set(True)
        # The save dialog already asked about replacing an existing file.
        self._confirmed_overwrite = True
        self._on_start()

    def apply_theme(self, palette: dict) -> None:
        pass