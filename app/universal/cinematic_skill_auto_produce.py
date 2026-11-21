"""Voice-led Cinematic Skill Auto Produce vertical slice.

This workflow starts from a user-supplied script and narration audio. It probes
the real audio duration, aligns the exact script locally, builds a Film from
measured narration cues, renders frames, and muxes the supplied audio track.
It intentionally does not invoke TTS, paid APIs, or remote services.
"""
from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional

from app.audio.ffmpeg_tool import FFmpegTool
from app.universal.cinematic_skill_adapter import (
    CinematicSkillRenderCoordinator,
    CinematicSkillRenderResult,
)
from app.universal.cinematic_skill_alignment import StableTsNarrationAligner
from app.universal.cinematic_skill_builder import CinematicSkillFilmBuilder
from app.universal.director_auto_produce_handoff import (
    DirectorHandoffError,
    build_cinematic_skill_handoff,
)
from app.workers.cancel import CancelToken


class CinematicSkillAutoProduceError(RuntimeError):
    """Raised when supplied script/audio cannot be produced safely."""


@dataclass(frozen=True)
class SuppliedNarrationMuxResult:
    video_codec: str
    audio_codec: str


class SuppliedNarrationMuxer:
    """Mux the original supplied audio into a rendered Film using FFmpeg.

    The Film's frame-quantized duration is authoritative for the MP4 container.
    If it exceeds the source audio by less than one frame, silence is padded at
    the tail; spoken samples are never time-stretched or shifted.
    """

    def __init__(self, ffmpeg: FFmpegTool) -> None:
        if not isinstance(ffmpeg, FFmpegTool):
            raise TypeError("ffmpeg must be an FFmpegTool")
        self._ffmpeg = ffmpeg

    def render(
        self,
        silent_video: Path,
        narration_audio: Path,
        audio_settings,
        destination: Path,
        plan,
        *,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> SuppliedNarrationMuxResult:
        del audio_settings  # Sound-design mixing is a later, explicit pipeline stage.
        silent_video = Path(silent_video)
        narration_audio = Path(narration_audio)
        destination = Path(destination)
        if not silent_video.is_file() or not narration_audio.is_file():
            raise CinematicSkillAutoProduceError("rendered video and supplied narration must both exist")
        fps = getattr(plan, "fps", None)
        frames = getattr(plan, "total_frames", None)
        if (
            isinstance(fps, bool) or not isinstance(fps, int) or fps <= 0
            or isinstance(frames, bool) or not isinstance(frames, int) or frames <= 0
        ):
            raise CinematicSkillAutoProduceError("mux timeline must contain positive fps and frame count")
        duration = frames / fps
        if not math.isfinite(duration) or duration <= 0:
            raise CinematicSkillAutoProduceError("mux timeline duration is invalid")
        if destination.exists() or destination.is_symlink():
            raise CinematicSkillAutoProduceError("refusing to overwrite an existing output")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.stem}.voxora-mux-",
            suffix=".part.mp4",
            dir=str(destination.parent),
        )
        os.close(fd)
        temporary = Path(temporary_name)
        temporary.unlink()
        try:
            if cancel is not None:
                cancel.raise_if_cancelled()
            if on_progress:
                on_progress(0.05, "Muxing supplied narration")
            args = [
                str(self._ffmpeg.require()), "-hide_banner", "-loglevel", "error",
                "-nostdin", "-n", "-i", str(silent_video), "-i", str(narration_audio),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-af", "apad",
                "-t", f"{duration:.9f}", "-movflags", "+faststart", str(temporary),
            ]
            self._ffmpeg.run_args(args, cancel=cancel, timeout=max(300.0, duration * 8))
            if cancel is not None:
                cancel.raise_if_cancelled()
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise CinematicSkillAutoProduceError("FFmpeg did not create a muxed MP4")
            media = self._ffmpeg.probe_structured(temporary, cancel=cancel)
            video = next((item for item in media.streams if item.codec_type == "video"), None)
            audio = next((item for item in media.streams if item.codec_type == "audio"), None)
            if video is None or audio is None:
                raise CinematicSkillAutoProduceError("final MP4 must contain both video and narration audio")
            if video.codec_name != "h264" or audio.codec_name != "aac":
                raise CinematicSkillAutoProduceError("final MP4 codecs failed H.264/AAC validation")
            if video.duration_s is not None and abs(video.duration_s - duration) > (1.0 / fps + 0.04):
                raise CinematicSkillAutoProduceError("final video duration does not match the Film timeline")
            os.replace(temporary, destination)
            if on_progress:
                on_progress(1.0, "Supplied narration mux complete")
            return SuppliedNarrationMuxResult(video.codec_name, audio.codec_name)
        finally:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class CinematicSkillAutoProduceResult:
    render: CinematicSkillRenderResult
    narration_duration_seconds: float
    aligned_line_count: int
    aligned_word_count: int
    language: str


class CinematicSkillAutoProduceWorkflow:
    """Coordinate supplied script + audio → measured Film → complete MP4."""

    def __init__(
        self,
        ffmpeg: FFmpegTool,
        *,
        aligner=None,
        film_builder=None,
        renderer=None,
    ) -> None:
        if not isinstance(ffmpeg, FFmpegTool):
            raise TypeError("ffmpeg must be an FFmpegTool")
        self._ffmpeg = ffmpeg
        self._aligner = aligner or StableTsNarrationAligner()
        self._film_builder = film_builder or CinematicSkillFilmBuilder()
        self._renderer = renderer or CinematicSkillRenderCoordinator()
        if not callable(getattr(self._aligner, "align", None)):
            raise TypeError("aligner must provide align(...)")
        if not callable(getattr(self._film_builder, "build", None)):
            raise TypeError("film_builder must provide build(...)")
        if not callable(getattr(self._renderer, "render", None)):
            raise TypeError("renderer must provide render(...)")

    def run(
        self,
        *,
        script: str,
        narration_audio: str | Path,
        language: str,
        project_dir: str | Path,
        destination: str | Path,
        fps: int = 30,
        width: int = 1280,
        height: int = 720,
        look: str = "studio",
        director_plan=None,
        source_unit_ids=None,
        profile_id: Optional[str] = None,
        director_plan_approved: bool = False,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> CinematicSkillAutoProduceResult:
        if not isinstance(script, str) or not script.strip():
            raise CinematicSkillAutoProduceError("script must not be empty")
        if not isinstance(language, str) or not language.strip():
            raise CinematicSkillAutoProduceError("language is required (for example 'en' or 'bn')")
        audio_path = Path(narration_audio).expanduser().resolve()
        if not audio_path.is_file():
            raise CinematicSkillAutoProduceError("supplied narration audio file does not exist")
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable")
        if cancel is not None:
            cancel.raise_if_cancelled()
        if on_progress:
            on_progress(0.02, "Inspecting supplied narration")
        info = self._ffmpeg.probe(audio_path, cancel=cancel)
        if not info.has_audio or info.duration_s is None or info.duration_s <= 0:
            raise CinematicSkillAutoProduceError("supplied file has no readable audio stream or duration")
        if on_progress:
            on_progress(0.08, "Aligning script to narration locally")
        project_root = Path(project_dir).expanduser().resolve()
        project_root.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix="voxora-auto-produce-", dir=str(project_root)))
        try:
            doc = self._aligner.align(
                script=script,
                audio_path=audio_path,
                language=language.strip(),
                project_dir=workspace,
                audio_duration_seconds=info.duration_s,
            )
            if cancel is not None:
                cancel.raise_if_cancelled()
            if on_progress:
                on_progress(0.18, "Building narration-led film")
            if director_plan is None:
                if source_unit_ids is not None or profile_id is not None or director_plan_approved:
                    raise CinematicSkillAutoProduceError(
                        "Director handoff metadata was supplied without a DirectorPlan"
                    )
                film = self._film_builder.build(doc, look=look, fps=fps)
            else:
                try:
                    director_shots = build_cinematic_skill_handoff(
                        director_plan,
                        script=script,
                        profile_id=profile_id,
                        narration_doc=doc,
                        source_unit_ids=source_unit_ids or (),
                        approved=director_plan_approved,
                    )
                except DirectorHandoffError as exc:
                    raise CinematicSkillAutoProduceError(
                        f"Director plan cannot enter Auto Produce: {exc}"
                    ) from exc
                film = self._film_builder.build(
                    doc, shots=director_shots, look=look, fps=fps,
                )
            frame_count = max(1, math.ceil(float(film.duration) * film.fps - 1e-9))
            timeline = SimpleNamespace(
                fps=film.fps, width=width, height=height, total_frames=frame_count,
            )
            if on_progress:
                on_progress(0.20, "Rendering and assembling MP4")
            render = self._renderer.render(
                film,
                destination,
                width=width,
                height=height,
                doc=doc,
                narration_wav=audio_path,
                audio_settings=object(),
                timeline_plan=timeline,
                audio_muxer=SuppliedNarrationMuxer(self._ffmpeg),
                cancel=cancel,
                on_progress=(
                    lambda fraction, message: on_progress(
                        0.20 + max(0.0, min(1.0, fraction)) * 0.80, message,
                    )
                ) if on_progress else None,
            )
            word_count = sum(len(line.word_timings) for line in doc.lines.values())
            return CinematicSkillAutoProduceResult(
                render=render,
                narration_duration_seconds=info.duration_s,
                aligned_line_count=len(doc.lines),
                aligned_word_count=word_count,
                language=language.strip(),
            )
        finally:
            import shutil
            shutil.rmtree(workspace, ignore_errors=True)
