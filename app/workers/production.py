from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from app.audio.assembler import WavBuilder
from app.audio.ffmpeg_tool import FFmpegTool
from app.audio.mixer import build_mix_args, has_mixing_work
from app.cache.video_cache import VideoCache
from app.core import constants
from app.core.exceptions import FFmpegError, MediaError, ProductionError
from app.core.logger import get_logger
from app.studio.models import StudioState
from app.studio.previews import probe_track_durations
from app.studio.timing import SceneTimingInput, VideoTimeline, compute_timeline
from app.core.timebase import frames_to_ticks, ticks_to_frames, ticks_to_samples, ticks_to_seconds
from app.video.render import (
    FILTER_SCRIPT_OPTIONS,
    SegmentSpec,
    build_concat_list,
    build_cut_join_args,
    build_mux_args,
    build_segment_args,
    build_xfade_join_args,
    build_xfade_script_ticks,
    is_unknown_option_error,
)
from app.workers.cancel import CancelToken
from app.workers.narration import NarrationJob, NarrationResult, SceneRequest

logger = get_logger("workers.production")


@dataclass(frozen=True)
class SceneInfo:
    """A project scene, in script order (video uses ALL scenes; narration only
    those with text)."""

    scene_id: str
    title: str
    text: str


@dataclass(frozen=True)
class ProductionOptions:
    render_video: bool = True
    export_audio: bool = False
    video_output: Optional[Path] = None
    audio_output: Optional[Path] = None
    audio_format: str = "mp3"  # "mp3" | "wav"


@dataclass(frozen=True)
class ProductionProgress:
    fraction: float
    stage: str
    message: str


@dataclass
class ProductionResult:
    video_path: Optional[Path]
    audio_path: Optional[Path]
    duration_s: float
    narration: NarrationResult
    timeline: Optional[VideoTimeline]
    segments_rendered: int = 0
    segments_cached: int = 0
    warnings: List[str] = field(default_factory=list)


class ProductionJob:
    """End-to-end pipeline: narration (existing NarrationJob, so cached audio
    is reused) -> timeline from REAL narration lengths -> aligned narration
    track -> optional music mix -> scene video segments (cached) -> join ->
    mux -> MP4 / MP3 / WAV. One cancel token governs every stage; every
    output is written as `<name>.part` and renamed only on success."""

    def __init__(
        self,
        narration_job: NarrationJob,
        ffmpeg: FFmpegTool,
        video_cache: VideoCache,
        temp_dir: Path,
    ) -> None:
        self._narration = narration_job
        self._ffmpeg = ffmpeg
        self._cache = video_cache
        self._temp_dir = Path(temp_dir)
        self._script_options = list(FILTER_SCRIPT_OPTIONS)  # best-working option first; reordered once learned

    async def run(
        self,
        requests: Sequence[SceneRequest],
        scenes: Sequence[SceneInfo],
        studio: StudioState,
        options: ProductionOptions,
        *,
        basename: str,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[ProductionProgress], None]] = None,
    ) -> ProductionResult:
        """on_progress may be called from background threads (the UI wraps it
        in AsyncBridge.dispatch)."""
        cancel = cancel or CancelToken()
        emit = on_progress or (lambda p: None)
        if not (options.render_video or options.export_audio):
            raise ProductionError("Choose at least one output: video (MP4) or audio (MP3/WAV).")
        if options.render_video and options.video_output is None:
            raise ProductionError("No MP4 output file was chosen.")
        if options.export_audio and options.audio_output is None:
            raise ProductionError("No audio output file was chosen.")
        await asyncio.to_thread(self._ffmpeg.require)

        narration_share = 0.35 if options.render_video else 0.6
        work = self._temp_dir / f"production_{uuid.uuid4().hex[:8]}"
        work.mkdir(parents=True, exist_ok=True)
        try:
            narration = await self._narration.run(
                requests, output_dir=work, basename=basename, cancel=cancel,
                on_progress=lambda ev: emit(ProductionProgress(ev.fraction * narration_share, "Narration", ev.message)),
            )
            cancel.raise_if_cancelled()
            return await asyncio.to_thread(
                self._produce, narration, scenes, studio, options, work, narration_share, cancel, emit
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)

    # ------------------------------------------------------------------
    # Blocking part (runs in a worker thread)
    # ------------------------------------------------------------------

    def _produce(self, narration, scenes, studio, options, work, start, cancel, emit) -> ProductionResult:
        warnings: List[str] = list(narration.warnings)
        audio_by_id = {a.scene_id: a for a in narration.scene_audio}
        video = studio.video

        def stage(name: str, lo: float, hi: float):
            def report(fraction: float, message: str = "") -> None:
                emit(ProductionProgress(lo + (hi - lo) * max(0.0, min(1.0, fraction)), name, message or name))
            return report

        # ---- timeline + the narration track every output is built on ----
        timeline: Optional[VideoTimeline] = None
        if options.render_video:
            inputs = []
            for scene in scenes:
                audio = audio_by_id.get(scene.scene_id)
                inputs.append(SceneTimingInput(
                    scene_id=scene.scene_id,
                    narration_s=audio.duration_s if audio else None,
                    configured_s=video.scene(scene.scene_id).duration_s,
                    pause_s=(audio.pause_ms / 1000.0) if audio else 0.0,
                ))
            timeline = compute_timeline(
                inputs, transition=video.transition, transition_s=video.transition_s,
                default_duration_s=video.default_duration_s,
            )
            titles = {s.scene_id: s.title for s in scenes}
            for slot in timeline.slots:
                if slot.extended:
                    warnings.append(
                        f"Scene '{titles.get(slot.scene_id, slot.scene_id)}': narration is longer than the "
                        f"configured duration, so the scene was extended to {slot.slot_s:.1f}s."
                    )
            narration_track = work / "narration_aligned.wav"
            with WavBuilder(narration_track, constants.NARRATION_SAMPLE_RATE) as builder:
                for slot in timeline.slots:
                    cancel.raise_if_cancelled()
                    audio = audio_by_id.get(slot.scene_id)
                    start_frame = ticks_to_frames(slot.start_ticks, video.fps, rounding="half_up")
                    end_frame = ticks_to_frames(slot.start_ticks + slot.slot_ticks, video.fps, rounding="half_up")
                    start_ticks = frames_to_ticks(start_frame, video.fps, rounding="half_up")
                    end_ticks = frames_to_ticks(end_frame, video.fps, rounding="half_up")
                    start_sample = ticks_to_samples(start_ticks, constants.NARRATION_SAMPLE_RATE, rounding="half_up")
                    end_sample = ticks_to_samples(end_ticks, constants.NARRATION_SAMPLE_RATE, rounding="half_up")
                    target_samples = max(0, end_sample - start_sample)
                    before_samples = builder.frames
                    if audio:
                        builder.add_wav(audio.wav_path)
                    used_samples = builder.frames - before_samples
                    builder.add_silence_samples(max(0, target_samples - used_samples))
            # Quantize the complete timeline once to the output frame grid.
            # All downstream video and mux durations derive from this frame count.
            fps = video.fps
            total_frames = max(1, ticks_to_frames(timeline.total_ticks, fps, rounding="half_up"))
            video_duration_ticks = frames_to_ticks(total_frames, fps, rounding="half_up")
            total_s = float(ticks_to_seconds(video_duration_ticks))
        else:
            narration_track = narration.wav_path
            total_s = narration.duration_seconds

        mix_lo = start
        mix_hi = start + (0.10 if options.render_video else 0.40)
        track_durations = probe_track_durations(self._ffmpeg, studio.audio)

        # ---- audio export ----
        audio_path: Optional[Path] = None
        if options.export_audio:
            audio_path = self._mix_to_file(
                narration_track, total_s, studio, track_durations, Path(options.audio_output),
                fmt=options.audio_format, sample_rate=constants.EXPORT_AUDIO_SAMPLE_RATE,
                cancel=cancel, report=stage("Audio export", mix_lo, mix_hi),
            )
        if not options.render_video:
            emit(ProductionProgress(1.0, "Done", "Audio exported."))
            return ProductionResult(None, audio_path, total_s, narration, None, warnings=warnings)

        # ---- audio for the video ----
        if has_mixing_work(studio.audio):
            video_audio = work / "video_audio.wav"
            self._mix_to_file(
                narration_track, total_s, studio, track_durations, video_audio, fmt="wav",
                sample_rate=constants.VIDEO_AUDIO_SAMPLE_RATE, cancel=cancel,
                report=stage("Audio mix", mix_lo, mix_hi), atomic=False,
            )
        else:
            video_audio = narration_track

        # ---- video ----
        assert timeline is not None
        rendered, reused = 0, 0
        segments: List[Path] = []
        width, height = video.size
        seg_lo, seg_hi = mix_hi, 0.85
        total_seg_time = sum(
            max(1, ticks_to_frames(slot.start_ticks + slot.segment_ticks, video.fps, rounding="half_up")
                - ticks_to_frames(slot.start_ticks, video.fps, rounding="half_up")) / video.fps
            for slot in timeline.slots
        ) or 1.0
        done_time = 0.0
        self._cache.remove_stale_parts()
        for scene, slot in zip(scenes, timeline.slots):
            cancel.raise_if_cancelled()
            start_frame = ticks_to_frames(slot.start_ticks, video.fps, rounding="half_up")
            end_frame = ticks_to_frames(
                slot.start_ticks + slot.segment_ticks, video.fps, rounding="half_up"
            )
            segment_frames = max(1, end_frame - start_frame)
            segment_ticks = frames_to_ticks(segment_frames, video.fps, rounding="half_up")
            segment_s = float(ticks_to_seconds(segment_ticks))
            spec = self._segment_spec(
                scene, segment_s, studio, width, height,
                length_ticks=segment_ticks, frame_count=segment_frames,
            )
            key = self._cache.segment_key(spec)
            label = f"Scene '{scene.title}'"
            lo = seg_lo + (seg_hi - seg_lo) * done_time / total_seg_time
            hi = seg_lo + (seg_hi - seg_lo) * (done_time + segment_s) / total_seg_time
            report = stage("Video scenes", lo, hi)
            if self._cache.has_segment(key):
                reused += 1
                report(1.0, f"{label}: reused cached video")
            else:
                part = self._cache.part_path(key)
                try:
                    self._ffmpeg.run_with_progress(
                        build_segment_args(self._ffmpeg.require(), spec, part), segment_s,
                        lambda f, lbl=label, rep=report: rep(f, f"Rendering {lbl}"), cancel,
                    )
                    self._cache.commit_segment(part, key)
                except BaseException:
                    part.unlink(missing_ok=True)
                    raise
                rendered += 1
            segments.append(self._cache.segment_path(key))
            done_time += segment_s

        joined = work / "joined.mp4"
        join_report = stage("Joining scenes", 0.85, 0.93)
        exe = self._ffmpeg.require()
        if len(segments) == 1:
            shutil.copyfile(segments[0], joined)
            join_report(1.0)
        elif timeline.transition_s > 0:
            script = work / "xfade.txt"
            start_frames = [ticks_to_frames(slot.start_ticks, video.fps, rounding="half_up")
                            for slot in timeline.slots]
            starts_ticks = [frames_to_ticks(frame, video.fps, rounding="half_up")
                            for frame in start_frames]
            transition_frames = ticks_to_frames(timeline.transition_ticks, video.fps, rounding="half_up")
            transition_ticks = frames_to_ticks(transition_frames, video.fps, rounding="half_up")
            script.write_text(build_xfade_script_ticks(starts_ticks, transition_ticks), encoding="utf-8")
            self._run_xfade_join(exe, segments, script, video.fps, joined, total_s,
                                 lambda f: join_report(f, "Crossfading scenes"), cancel)
        else:
            listing = work / "segments.txt"
            listing.write_text(build_concat_list(segments), encoding="utf-8")
            self._ffmpeg.run_with_progress(
                build_cut_join_args(exe, listing, joined), total_s,
                lambda f: join_report(f, "Joining scenes"), cancel,
            )

        video_path = Path(options.video_output)
        video_path.parent.mkdir(parents=True, exist_ok=True)
        part_video = video_path.with_name(video_path.name + ".part")
        mux_report = stage("Final video", 0.93, 1.0)
        try:
            self._ffmpeg.run_with_progress(
                build_mux_args(
                    exe, joined, video_audio, total_s, part_video,
                    frame_count=total_frames, duration_ticks=video_duration_ticks,
                ), total_s,
                lambda f: mux_report(f, "Writing final MP4"), cancel,
            )
            if not part_video.is_file() or part_video.stat().st_size == 0:
                raise ProductionError("The video file was not created.")
            rendered_info = self._ffmpeg.probe(part_video)
            duration_tolerance = (1.0 / video.fps) + 0.03  # one frame plus AAC packet tolerance
            actual_duration = rendered_info.duration_s
            if (
                rendered_info.kind != "video"
                or actual_duration is None
                or abs(actual_duration - total_s) > duration_tolerance
            ):
                actual_label = f"{actual_duration:.6f}s" if actual_duration is not None else "unknown"
                raise ProductionError(
                    "The rendered MP4 duration does not match the frame-aligned project timeline "
                    f"(expected {total_s:.6f}s, got {actual_label})."
                )
            os.replace(part_video, video_path)
        except BaseException:
            part_video.unlink(missing_ok=True)
            raise
        self._cache.prune()
        emit(ProductionProgress(1.0, "Done", "Video rendered."))
        return ProductionResult(
            video_path, audio_path, total_s, narration, timeline,
            segments_rendered=rendered, segments_cached=reused, warnings=warnings,
        )

    # ------------------------------------------------------------------

    def _mix_to_file(
        self, narration_track, total_s, studio, track_durations, dest: Path,
        *, fmt, sample_rate, cancel, report, atomic: bool = True,
    ) -> Path:
        exe = self._ffmpeg.require()
        dest.parent.mkdir(parents=True, exist_ok=True)
        target = dest.with_name(dest.name + ".part") if atomic else dest
        args = build_mix_args(
            exe, narration_track, total_s, studio.audio, track_durations, target,
            fmt=fmt, sample_rate=sample_rate, mp3_bitrate=constants.EXPORT_MP3_BITRATE,
        )
        try:
            self._ffmpeg.run_with_progress(args, total_s, lambda f: report(f, "Mixing audio"), cancel)
            if not target.is_file() or target.stat().st_size == 0:
                raise ProductionError("The audio file was not created.")
            if atomic:
                os.replace(target, dest)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return dest

    def _run_xfade_join(self, exe, segments, script, fps, dest, total_s, on_progress, cancel) -> None:
        """Run the crossfade join with whichever filter-script option this
        FFmpeg understands (new `-/filter_complex`, or the old
        `-filter_complex_script`). The one that works is remembered."""
        last_error: Optional[FFmpegError] = None
        for option in list(self._script_options):
            try:
                self._ffmpeg.run_with_progress(
                    build_xfade_join_args(exe, segments, script, fps, dest, option), total_s, on_progress, cancel,
                )
            except FFmpegError as exc:
                if not is_unknown_option_error(str(exc)):
                    raise
                logger.info("FFmpeg does not accept %s; trying the next form.", option)
                last_error = exc
                dest.unlink(missing_ok=True)
                continue
            if option != self._script_options[0]:
                self._script_options.remove(option)
                self._script_options.insert(0, option)
            return
        raise ProductionError(
            "This FFmpeg build does not support the crossfade filter options Voxora Studio uses. "
            "Update FFmpeg or switch the transition to 'cut' on the Video Settings tab."
        ) from last_error

    def _segment_spec(
        self, scene: SceneInfo, length_s: float, studio: StudioState, width: int, height: int,
        *, length_ticks: Optional[int] = None, frame_count: Optional[int] = None,
    ) -> SegmentSpec:
        video = studio.video
        setting = video.scene(scene.scene_id)
        motion = setting.motion or video.default_motion
        fit = setting.fit or video.default_fit
        timing = {"length_ticks": length_ticks, "frame_count": frame_count}
        if not setting.media_path:
            return SegmentSpec("blank", None, length_s, width, height, video.fps, **timing)
        try:
            info = self._ffmpeg.probe(Path(setting.media_path))
        except MediaError as exc:
            raise ProductionError(f"Scene '{scene.title}': {exc}") from exc
        if info.kind == "image":
            return SegmentSpec("image", setting.media_path, length_s, width, height, video.fps, motion, fit, **timing)
        if info.kind == "video":
            return SegmentSpec("video", setting.media_path, length_s, width, height, video.fps, "none", fit, **timing)
        raise ProductionError(f"Scene '{scene.title}': '{Path(setting.media_path).name}' is not an image or video file.")