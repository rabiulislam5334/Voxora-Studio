from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tkinter as tk
import uuid
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.core.logger import get_logger
from app.universal.asset_library import VisualAssetLibrary
from app.universal.auto_produce_plan import create_auto_produce_plan
from app.universal.cinematic_skill_auto_produce import CinematicSkillAutoProduceWorkflow
from app.universal.models import UniversalState
from app.universal.profiles.models import ChannelProfile
from app.universal.supplied_narration_input import build_line_aligned_narration_source
from app.workers.cancel import CancelToken

logger = get_logger("ui.auto_produce")


class AutoProduceTab(ttk.Frame):
    """One-action supplied script + narration → Director-led MP4 workspace.

    This is an initial UI bridge to the existing Cinematic Skill workflow.
    It deliberately does not claim Render Orchestrator, motion, caption or
    sound-design integration that has not yet been implemented.
    """

    def __init__(self, master: tk.Widget, ctx) -> None:
        super().__init__(master, style="App.TFrame", padding=18)
        self._ctx = ctx
        self._token: CancelToken | None = None
        self.running = False
        self._last_dir: Path | None = None
        self._target_path: Path | None = None
        self._staging_path: Path | None = None
        self._audio_var = tk.StringVar()
        self._visual_direction_var = tk.StringVar()
        self._language_var = tk.StringVar(value="en")
        self._folder_var = tk.StringVar(value=str(ctx.config.output_dir))
        self._name_var = tk.StringVar()
        self._profile_var = tk.StringVar(value="No applied channel profile")
        self._script_var = tk.StringVar(value="Script: not checked")
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Auto Produce", style="PageTitle.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            self,
            text="Use the project's script and an existing narration recording. Voxora keeps the supplied voice; "
                 "it does not generate replacement TTS audio in this workflow.",
            style="Muted.TLabel", wraplength=900, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        inputs = ttk.Frame(self, style="App.TFrame")
        inputs.grid(row=2, column=0, sticky="ew")
        inputs.columnconfigure(1, weight=1)
        ttk.Label(inputs, text="Narration audio", style="App.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(inputs, textvariable=self._audio_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(inputs, text="Browse...", style="Secondary.TButton", command=self._browse_audio).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Label(inputs, text="Language code", style="App.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        ttk.Entry(inputs, textvariable=self._language_var, width=12).grid(
            row=1, column=1, sticky="w", pady=(10, 0)
        )
        ttk.Label(inputs, text="Output folder", style="App.TLabel").grid(
            row=2, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        ttk.Entry(inputs, textvariable=self._folder_var).grid(row=2, column=1, sticky="ew", pady=(10, 0))
        ttk.Button(inputs, text="Browse...", style="Secondary.TButton", command=self._browse_folder).grid(
            row=2, column=2, padx=(8, 0), pady=(10, 0)
        )
        ttk.Label(inputs, text="File name", style="App.TLabel").grid(
            row=3, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        ttk.Entry(inputs, textvariable=self._name_var, width=42).grid(
            row=3, column=1, sticky="w", pady=(10, 0)
        )
        ttk.Label(inputs, text="Visual direction JSON (optional)", style="App.TLabel").grid(
            row=4, column=0, sticky="w", padx=(0, 10), pady=(10, 0)
        )
        ttk.Entry(inputs, textvariable=self._visual_direction_var).grid(
            row=4, column=1, sticky="ew", pady=(10, 0)
        )
        ttk.Button(
            inputs, text="Browse JSON...", style="Secondary.TButton",
            command=self._browse_visual_direction,
        ).grid(row=4, column=2, padx=(8, 0), pady=(10, 0))
        ttk.Button(
            inputs, text="Clear", style="Secondary.TButton",
            command=lambda: self._visual_direction_var.set(""),
        ).grid(row=4, column=3, padx=(6, 0), pady=(10, 0))

        info = ttk.Frame(self, style="Card.TFrame", padding=12)
        info.grid(row=3, column=0, sticky="ew", pady=(16, 10))
        ttk.Label(info, textvariable=self._profile_var, style="App.TLabel").pack(anchor="w")
        ttk.Label(info, textvariable=self._script_var, style="Muted.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(
            info,
            text="A local alignment runtime (Stable-ts) and the optional Cinematic Skill renderer are required. "
                 "No paid API or network generation is enabled by this tab.",
            style="Muted.TLabel", wraplength=880, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        actions = ttk.Frame(self, style="App.TFrame")
        actions.grid(row=4, column=0, sticky="ew", pady=(4, 8))
        ttk.Button(actions, text="Check Inputs", style="Secondary.TButton", command=self.refresh).pack(side="left")
        self._start_btn = ttk.Button(
            actions, text="Generate Video", style="Primary.TButton", command=self._on_start
        )
        self._start_btn.pack(side="left", padx=8)
        self._cancel_btn = ttk.Button(
            actions, text="Cancel", style="Secondary.TButton", command=self._on_cancel, state="disabled"
        )
        self._cancel_btn.pack(side="left")
        self._open_btn = ttk.Button(
            actions, text="Open Output Folder", style="Secondary.TButton",
            command=self._open_folder, state="disabled",
        )
        self._open_btn.pack(side="left", padx=8)

        self._progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self._progress.grid(row=5, column=0, sticky="ew", pady=(8, 2))
        self._stage = ttk.Label(self, text="Ready", style="App.TLabel")
        self._stage.grid(row=6, column=0, sticky="w")
        self._message = ttk.Label(self, text="", style="Muted.TLabel", wraplength=900, justify="left")
        self._message.grid(row=7, column=0, sticky="w", pady=(4, 0))

    def _browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose supplied narration audio",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.aac *.flac *.ogg"), ("All files", "*.*")],
        )
        if path:
            self._audio_var.set(path)

    def _browse_visual_direction(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose external visual-direction package",
            filetypes=[("Visual direction JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self._visual_direction_var.set(path)
            self._message.configure(text="Visual-direction package selected. It will be validated against the current script, narration source and profile before approval.")

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(
            title="Choose MP4 output folder", initialdir=self._folder_var.get() or None
        )
        if path:
            self._folder_var.set(path)

    def _safe_name(self, value: str) -> str:
        cleaned = "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in value)
        return cleaned.strip(" .") or "voxora-video"

    def _script_and_profile(self):
        project = self._ctx.project()
        scenes = self._ctx.scenes()
        script = "\n\n".join(scene.text.strip() for scene in scenes if scene.text.strip())
        if not script:
            raise ValueError("The current project has no script text.")
        state = UniversalState.from_project_settings(project.settings)
        if state.read_only:
            raise ValueError("The project's Universal profile settings are read-only or unsupported.")
        snapshot = state.profile_snapshot
        if snapshot is None or snapshot.read_only:
            raise ValueError("Apply a Channel Profile to this project before Auto Produce.")
        profile_data = dict(snapshot.profile_data)
        selected_preset_id = snapshot.selected_preset_id
        if selected_preset_id:
            preset = next(
                (item for item in profile_data.get("presets", []) if item.get("preset_id") == selected_preset_id),
                None,
            )
            if preset:
                base_visual = profile_data.get("visual_defaults", {})
                preset_visual = preset.get("visual_defaults", {})
                profile_data["visual_defaults"] = {
                    "style_family": (
                        preset_visual.get("style_family", "unspecified")
                        if preset_visual.get("style_family", "unspecified") != "unspecified"
                        else base_visual.get("style_family", "unspecified")
                    ),
                    "style_tags": list(dict.fromkeys((*base_visual.get("style_tags", []), *preset_visual.get("style_tags", [])))),
                    "mood": list(dict.fromkeys((*base_visual.get("mood", []), *preset_visual.get("mood", [])))),
                    "composition_guidance": list(dict.fromkeys((*base_visual.get("composition_guidance", []), *preset_visual.get("composition_guidance", [])))),
                }
                profile_data["narration_defaults"] = {
                    **profile_data.get("narration_defaults", {}),
                    **preset.get("narration_defaults", {}),
                }
        profile = ChannelProfile.from_dict(profile_data)
        if profile.read_only or profile.profile_id != state.profile_id:
            raise ValueError("The saved Channel Profile snapshot is unsupported or inconsistent.")
        return script, profile

    def refresh(self) -> None:
        if not self._name_var.get().strip():
            self._name_var.set(self._safe_name(self._ctx.script.get_project_name()))
        try:
            script, profile = self._script_and_profile()
        except (TypeError, ValueError) as exc:
            self._profile_var.set("Channel profile: not ready")
            self._script_var.set("Script: not ready")
            self._message.configure(text=str(exc))
            return
        self._profile_var.set(f"Applied profile: {profile.display_name} ({profile.profile_id})")
        self._script_var.set(f"Script: {len(script)} characters · {len(script.split())} words · "
                             f"{sum(1 for line in script.splitlines() if line.strip())} non-empty lines")
        self._message.configure(text="Ready to review the generated Director plan.")

    def _on_start(self) -> None:
        if self.running:
            return
        if self._ctx.voice.is_busy():
            self._message.configure(text="Another narration or production job is running. Wait for it to finish.")
            return
        audio = Path(self._audio_var.get().strip()).expanduser()
        if not audio.is_file():
            self._message.configure(text="Choose an existing narration audio file first.")
            return
        language = self._language_var.get().strip()
        if not language:
            self._message.configure(text="Enter the narration language code (for example en or bn).")
            return
        try:
            script, profile = self._script_and_profile()
            aligned_script, narration_source = build_line_aligned_narration_source(
                script, language=language,
            )
            visual_direction_path = self._visual_direction_var.get().strip()
            plan = create_auto_produce_plan(
                narration_source,
                profile,
                visual_direction_path=visual_direction_path or None,
            )
        except Exception as exc:
            self._message.configure(text=str(exc))
            return

        preview_lines = [
            f"{shot.shot_type}: {shot.visual_prompt}"
            for shot in plan.shots[:8]
        ]
        plan_origin = (
            "External visual-direction package" if visual_direction_path
            else "Internal Production Director"
        )
        preview = (
            f"Plan source: {plan_origin}\n"
            f"Profile: {profile.display_name}\n"
            f"Scenes: {len(plan.scenes)} · Shots: {len(plan.shots)}\n\n"
            + "\n".join(preview_lines)
        )
        if len(plan.shots) > 8:
            preview += f"\n… and {len(plan.shots) - 8} more shots."
        if not messagebox.askyesno(
            "Review and approve Director plan",
            preview + "\n\nApprove this plan and start automatic production?",
            parent=self,
        ):
            return

        folder = Path(self._folder_var.get().strip() or self._ctx.config.output_dir)
        destination = folder / f"{self._safe_name(self._name_var.get() or self._ctx.script.get_project_name())}.mp4"
        if destination.is_symlink() or (destination.exists() and not destination.is_file()):
            self._message.configure(text="The output path must be a regular file, not a symbolic link or directory.")
            return
        if destination.exists() and not messagebox.askyesno(
            "Replace existing video?",
            f"The output already exists:\n{destination}\n\nReplace it after a new render succeeds?",
            parent=self,
        ):
            return

        try:
            folder.mkdir(parents=True, exist_ok=True)
            self._target_path = destination
            self._staging_path = folder / f".{destination.stem}.{uuid.uuid4().hex}.part.mp4"
            library = VisualAssetLibrary(Path(self._ctx.config.assets_dir) / "visual_library")
            workflow = CinematicSkillAutoProduceWorkflow(self._ctx.ffmpeg)
            self._token = CancelToken()
            self.running = True
            self._ctx.voice.set_external_busy(True)
            self._set_running(True)
            self._last_dir = folder
            self._progress.configure(value=0)
            self._stage.configure(text="Starting Auto Produce...")
            self._message.configure(text=f"Aligning supplied narration and preparing the approved {plan_origin.lower()} plan.")
            runner = partial(
                workflow.run,
                script=aligned_script,
                narration_audio=audio,
                language=language,
                project_dir=Path(self._ctx.config.temp_dir) / "auto_produce",
                destination=self._staging_path,
                fps=profile.production_defaults.frame_rate or 30,
                width=1280,
                height=720,
                director_plan=plan,
                narration_source=narration_source,
                profile_id=profile.profile_id,
                director_plan_approved=True,
                profile=profile,
                asset_library=library,
                allow_network=False,
                allow_api_key=False,
                cancel=self._token,
                on_progress=lambda fraction, message: self._ctx.bridge.dispatch(
                    self._apply_progress, fraction, message,
                ),
            )
            self._ctx.bridge.run_coroutine(
                asyncio.to_thread(runner),
                on_success=self._on_done,
                on_error=self._on_failed,
            )
        except Exception as exc:
            self._finish()
            self._message.configure(text=f"Could not start Auto Produce: {exc}")

    def _apply_progress(self, fraction: float, message: str) -> None:
        if not self.running:
            return
        self._progress.configure(value=max(0.0, min(100.0, fraction * 100)))
        self._stage.configure(text=f"{int(fraction * 100)}%")
        self._message.configure(text=message)

    def _on_cancel(self) -> None:
        if self._token is not None and not self._token.cancelled:
            self._token.cancel()
            self._cancel_btn.configure(state="disabled")
            self._message.configure(text="Cancelling Auto Produce...")

    def _finish(self) -> None:
        self.running = False
        self._token = None
        self._ctx.voice.set_external_busy(False)
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self._start_btn.configure(state="disabled" if running else "normal")
        self._cancel_btn.configure(state="normal" if running else "disabled")

    def _on_done(self, result) -> None:
        try:
            if self._target_path is None:
                raise OSError("Auto Produce output destination was lost.")
            os.replace(result.render.destination, self._target_path)
            final_path = self._target_path
            self._staging_path = None
        except OSError as exc:
            if self._staging_path is not None:
                try:
                    self._staging_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove failed Auto Produce staging file: %s", self._staging_path)
                self._staging_path = None
            self._finish()
            self._stage.configure(text="Failed")
            self._message.configure(text=f"Render completed, but the final MP4 could not be committed: {exc}")
            self._ctx.on_status("Auto Produce output commit failed.")
            return
        self._finish()
        self._progress.configure(value=100)
        self._stage.configure(text="Finished")
        self._message.configure(
            text=f"Finished MP4: {final_path}\n"
                 f"Duration: {result.narration_duration_seconds:.1f}s · "
                 f"Aligned lines: {result.aligned_line_count} · "
                 f"Words: {result.aligned_word_count}"
        )
        self._open_btn.configure(state="normal")
        self._ctx.on_status("Supplied-narration Auto Produce finished.")
        messagebox.showinfo(
            "Auto Produce complete",
            f"Finished MP4:\n{final_path}\n\n"
            "The original supplied narration was used as the final audio track.",
            parent=self,
        )

    def _on_failed(self, error: Exception) -> None:
        self._finish()
        if self._staging_path is not None:
            try:
                self._staging_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove failed Auto Produce staging file: %s", self._staging_path)
            self._staging_path = None
        self._progress.configure(value=0)
        self._stage.configure(text="Failed")
        self._message.configure(text=str(error))
        self._ctx.on_status("Supplied-narration Auto Produce failed.")
        logger.error("Auto Produce failed: %s", error)

    def _open_folder(self) -> None:
        folder = self._last_dir
        if folder is None or not folder.exists():
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            self._message.configure(text=f"Could not open output folder: {exc}")

    def shutdown(self) -> None:
        if self._token is not None:
            self._token.cancel()
