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
from dataclasses import dataclass, replace
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
from app.universal.director_visual_acquisition import (
    DirectorVisualResolution,
    ShotVisualAcquisitionError,
    resolve_director_plan_visuals,
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
    visual_resolution: Optional[DirectorVisualResolution] = None


class CinematicSkillAutoProduceWorkflow:
    """Coordinate supplied script + audio → measured Film → complete MP4."""

    def __init__(
        self,
        ffmpeg: FFmpegTool,
        *,
        aligner=None,
        film_builder=None,
        renderer=None,
        visual_resolver=None,
    ) -> None:
        if not isinstance(ffmpeg, FFmpegTool):
            raise TypeError("ffmpeg must be an FFmpegTool")
        self._ffmpeg = ffmpeg
        self._aligner = aligner or StableTsNarrationAligner()
        self._film_builder = film_builder or CinematicSkillFilmBuilder()
        self._renderer = renderer or CinematicSkillRenderCoordinator()
        self._visual_resolver = visual_resolver or resolve_director_plan_visuals
        if not callable(getattr(self._aligner, "align", None)):
            raise TypeError("aligner must provide align(...)")
        if not callable(getattr(self._film_builder, "build", None)):
            raise TypeError("film_builder must provide build(...)")
        if not callable(getattr(self._renderer, "render", None)):
            raise TypeError("renderer must provide render(...)")
        if not callable(self._visual_resolver):
            raise TypeError("visual_resolver must be callable")

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
        narration_source=None,
        profile_id: Optional[str] = None,
        director_plan_approved: bool = False,
        profile=None,
        asset_library=None,
        generation_runtime=None,
        visual_provider_id: Optional[str] = None,
        allow_network: bool = False,
        allow_api_key: bool = False,
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
        if (profile is None) != (asset_library is None):
            raise CinematicSkillAutoProduceError(
                "profile and asset_library must be supplied together for Director visual resolution"
            )
        if profile is None and (
            generation_runtime is not None or visual_provider_id is not None
            or allow_network or allow_api_key
        ):
            raise CinematicSkillAutoProduceError(
                "visual generation options require both profile and asset_library"
            )
        if not isinstance(allow_network, bool) or not isinstance(allow_api_key, bool):
            raise CinematicSkillAutoProduceError("visual network/API-key consent flags must be booleans")
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
            visual_resolution = None
            if on_progress:
                on_progress(
                    0.18,
                    "Resolving approved Director visuals" if profile is not None
                    else "Building narration-led film",
                )
            if director_plan is None:
                if (
                    narration_source is not None or profile_id is not None or director_plan_approved
                    or profile is not None or asset_library is not None
                    or generation_runtime is not None or visual_provider_id is not None
                ):
                    raise CinematicSkillAutoProduceError(
                        "Director handoff or visual-resolution metadata was supplied without a DirectorPlan"
                    )
                film = self._film_builder.build(doc, look=look, fps=fps)
            else:
                try:
                    director_shots = build_cinematic_skill_handoff(
                        director_plan,
                        script=script,
                        profile_id=profile_id,
                        narration_doc=doc,
                        narration_source=narration_source,
                        approved=director_plan_approved,
                    )
                except DirectorHandoffError as exc:
                    raise CinematicSkillAutoProduceError(
                        f"Director plan cannot enter Auto Produce: {exc}"
                    ) from exc
                if profile is not None:
                    if getattr(profile, "profile_id", None) != profile_id:
                        raise CinematicSkillAutoProduceError(
                            "active ChannelProfile does not match profile_id"
                        )
                    try:
                        visual_resolution = self._visual_resolver(
                            director_plan,
                            script=script,
                            narration_source=narration_source,
                            profile=profile,
                            asset_library=asset_library,
                            approved=director_plan_approved,
                            generation_runtime=generation_runtime,
                            provider_id=visual_provider_id,
                            allow_network=allow_network,
                            allow_api_key=allow_api_key,
                            progress=(
                                (lambda fraction, message: on_progress(
                                    0.18 + max(0.0, min(1.0, float(fraction))) * 0.03,
                                    message,
                                )) if on_progress else None
                            ),
                        )
                    except ShotVisualAcquisitionError as exc:
                        raise CinematicSkillAutoProduceError(
                            f"Director visual resolution failed: {exc}"
                        ) from exc
                    if not isinstance(visual_resolution, DirectorVisualResolution):
                        raise CinematicSkillAutoProduceError(
                            "visual resolver returned an invalid resolution object"
                        )
                    if (
                        visual_resolution.plan_id != director_plan.plan_id
                        or visual_resolution.source_fingerprint != director_plan.source_fingerprint
                        or visual_resolution.profile_id != director_plan.profile_id
                    ):
                        raise CinematicSkillAutoProduceError(
                            "visual resolution provenance does not match the approved DirectorPlan"
                        )
                    expected_shot_ids = tuple(item.shot_id for item in director_plan.shots)
                    resolved_shot_ids = tuple(item.shot_id for item in visual_resolution.shots)
                    if resolved_shot_ids != expected_shot_ids:
                        raise CinematicSkillAutoProduceError(
                            "visual resolution must contain every Director shot exactly once and in order"
                        )
                    resolution_by_shot = {item.shot_id: item for item in visual_resolution.shots}
                    resolved_director_shots = []
                    for item in director_shots:
                        resolution = resolution_by_shot.get(item.director_shot_id)
                        if resolution is None:
                            raise CinematicSkillAutoProduceError(
                                "a Film shot is missing its Director visual resolution"
                            )
                        if resolution.status in {"selected", "generated"}:
                            if not resolution.asset_id or not resolution.asset_path:
                                raise CinematicSkillAutoProduceError(
                                    "resolved visual is missing its asset ID or local path"
                                )
                            item = replace(item, kind="image", image_path=resolution.asset_path)
                        elif resolution.status == "unresolved":
                            if resolution.asset_id is not None or resolution.asset_path is not None:
                                raise CinematicSkillAutoProduceError(
                                    "unresolved visual results must not carry an asset ID or path"
                                )
                        else:
                            raise CinematicSkillAutoProduceError(
                                f"unsupported visual resolution status: {resolution.status!r}"
                            )
                        resolved_director_shots.append(item)
                    director_shots = tuple(resolved_director_shots)
                if on_progress:
                    on_progress(0.22, "Building narration-led film")
                film = self._film_builder.build(
                    doc, shots=director_shots, look=look, fps=fps,
                )
            frame_count = max(1, math.ceil(float(film.duration) * film.fps - 1e-9))
            timeline = SimpleNamespace(
                fps=film.fps, width=width, height=height, total_frames=frame_count,
            )
            render_start = 0.22 if director_plan is not None and profile is not None else 0.20
            if on_progress:
                on_progress(render_start, "Rendering and assembling MP4")
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
                        render_start + max(0.0, min(1.0, fraction)) * (1.0 - render_start), message,
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
                visual_resolution=visual_resolution,
            )
        finally:
            import shutil
            shutil.rmtree(workspace, ignore_errors=True)
