"""Audio mix and final MP4 mux for composition-backed Universal timelines.

This module deliberately reuses the existing Studio AudioSettings, audio mixer,
FFmpegTool, and video mux command. It does not introduce a second mixer or alter
the legacy ProductionJob pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
import os
from pathlib import Path
from typing import Callable, Mapping, Optional

from app.audio.ffmpeg_tool import FFmpegTool
from app.audio.mixer import build_mix_args, has_mixing_work
from app.core import constants
from app.core.exceptions import ProductionError
from app.core.timebase import frames_to_ticks, ticks_to_seconds
from app.studio.models import AudioSettings
from app.studio.previews import probe_track_durations
from app.universal.composition_timeline import CompositionTimelinePlan
from app.video.render import build_mux_args
from app.workers.cancel import CancelToken


class CompositionAudioMuxError(ProductionError):
    """Composition audio/mux input, execution, or output validation failure."""


@dataclass(frozen=True)
class CompositionAudioMuxResult:
    destination: Path
    duration_ticks: int
    duration_seconds: float
    frame_count: int
    mixed_audio: bool
    video_codec: str
    audio_codec: str


def composition_video_duration(plan: CompositionTimelinePlan) -> tuple[int, float]:
    """Return the frame-quantized output duration, not the unrounded plan duration."""
    if not isinstance(plan, CompositionTimelinePlan):
        raise TypeError("plan must be a CompositionTimelinePlan")
    if not plan.is_valid:
        raise CompositionAudioMuxError("composition timeline contains blocking diagnostics")
    if isinstance(plan.fps, bool) or not isinstance(plan.fps, int) or plan.fps <= 0:
        raise CompositionAudioMuxError("composition timeline FPS must be a positive integer")
    if isinstance(plan.total_frames, bool) or not isinstance(plan.total_frames, int) or plan.total_frames <= 0:
        raise CompositionAudioMuxError("composition timeline must contain at least one output frame")
    duration_ticks = frames_to_ticks(plan.total_frames, plan.fps, rounding="half_up")
    return duration_ticks, float(ticks_to_seconds(duration_ticks))


def build_composition_audio_mix_args(
    ffmpeg_executable: Path,
    narration_wav: Path,
    plan: CompositionTimelinePlan,
    audio: AudioSettings,
    track_durations: Mapping[str, float],
    destination: Path,
) -> list[str]:
    """Build the existing Studio mixer command for the exact video duration."""
    _duration_ticks, duration_s = composition_video_duration(plan)
    if not isinstance(audio, AudioSettings):
        raise TypeError("audio must be AudioSettings")
    return build_mix_args(
        ffmpeg_executable, Path(narration_wav), duration_s, audio,
        dict(track_durations), Path(destination), fmt="wav",
        sample_rate=constants.VIDEO_AUDIO_SAMPLE_RATE,
    )


def build_composition_video_mux_args(
    ffmpeg_executable: Path,
    silent_video: Path,
    mixed_audio: Path,
    plan: CompositionTimelinePlan,
    destination: Path,
) -> list[str]:
    """Build the existing lossless-video-copy/AAC mux for this timeline."""
    duration_ticks, duration_s = composition_video_duration(plan)
    return build_mux_args(
        ffmpeg_executable, Path(silent_video), Path(mixed_audio), duration_s,
        Path(destination), frame_count=plan.total_frames,
        duration_ticks=duration_ticks,
    )


def _cancel(cancel: Optional[CancelToken]) -> None:
    if cancel is not None:
        cancel.raise_if_cancelled()


def _validate_silent_video(
    ffmpeg: FFmpegTool, path: Path, plan: CompositionTimelinePlan,
    cancel: Optional[CancelToken],
) -> None:
    _cancel(cancel)
    info = ffmpeg.probe_structured(path, count_packets=True, cancel=cancel)
    if len(info.streams) != 1:
        raise CompositionAudioMuxError("input visual MP4 must contain exactly one silent video stream")
    stream = info.streams[0]
    try:
        rate = Fraction(stream.avg_frame_rate) if stream.avg_frame_rate else None
    except (ValueError, ZeroDivisionError):
        rate = None
    if (
        stream.codec_type != "video" or stream.codec_name != "h264"
        or stream.width != plan.width or stream.height != plan.height
        or rate != Fraction(plan.fps, 1)
        or stream.packet_count != plan.total_frames
    ):
        raise CompositionAudioMuxError(
            "input visual MP4 does not match the composition timeline's H.264 dimensions, FPS, or frame count"
        )


def _validate_final_mp4(
    ffmpeg: FFmpegTool, path: Path, plan: CompositionTimelinePlan,
    duration_s: float, cancel: Optional[CancelToken],
) -> tuple[str, str]:
    _cancel(cancel)
    info = ffmpeg.probe_structured(path, count_packets=True, cancel=cancel)
    videos = [item for item in info.streams if item.codec_type == "video"]
    audios = [item for item in info.streams if item.codec_type == "audio"]
    if len(info.streams) != 2 or len(videos) != 1 or len(audios) != 1:
        raise CompositionAudioMuxError("final MP4 must contain exactly one video stream and one audio stream")
    video, audio = videos[0], audios[0]
    try:
        rate = Fraction(video.avg_frame_rate) if video.avg_frame_rate else None
    except (ValueError, ZeroDivisionError):
        rate = None
    if (
        video.codec_name != "h264" or video.width != plan.width or video.height != plan.height
        or rate != Fraction(plan.fps, 1) or video.packet_count != plan.total_frames
    ):
        raise CompositionAudioMuxError("final MP4 video stream does not match the approved timeline")
    if audio.codec_name != "aac":
        raise CompositionAudioMuxError("final MP4 audio stream is not AAC")
    _cancel(cancel)
    timestamps = ffmpeg.probe_frame_timestamps(path, plan.fps, cancel=cancel)
    tolerance = (1.0 / plan.fps) + 0.03
    if (
        timestamps.frame_count != plan.total_frames
        or timestamps.missing_timestamp_count
        or timestamps.non_monotonic_count
        or timestamps.cfr_interval_mismatch_count
    ):
        raise CompositionAudioMuxError("final MP4 video frame timestamps are incomplete or not constant-frame-rate")
    for label, value in (
        ("container", info.format_duration_s),
        ("video stream", video.duration_s),
        ("audio stream", audio.duration_s),
    ):
        allowed = tolerance
        if label == "audio stream" and audio.codec_name == "aac" and audio.sample_rate:
            allowed = (1025 / audio.sample_rate)
        if value is None or not math.isfinite(value) or abs(value - duration_s) > allowed:
            raise CompositionAudioMuxError(f"final MP4 {label} duration does not match the composition timeline")
    for label, value in (("video", video.start_time_s), ("audio", audio.start_time_s)):
        if value is None or abs(value) > tolerance:
            raise CompositionAudioMuxError(f"final MP4 {label} stream does not start at timeline zero")
    return video.codec_name or "unknown", audio.codec_name or "unknown"


class CompositionAudioMuxer:
    """Reuse Studio's current music mixer and final video mux for a silent MP4.

    The narration WAV must already be aligned to the frame-quantized timeline.
    The caller owns frame rendering/encoding and must explicitly invoke this
    method after reviewing the immutable timeline plan.
    """

    def __init__(self, ffmpeg: FFmpegTool) -> None:
        if not isinstance(ffmpeg, FFmpegTool):
            raise TypeError("ffmpeg must be an FFmpegTool")
        self._ffmpeg = ffmpeg

    def render(
        self,
        silent_video: Path,
        narration_wav: Path,
        audio: AudioSettings,
        destination: Path,
        plan: CompositionTimelinePlan,
        *,
        track_durations: Optional[Mapping[str, float]] = None,
        cancel: Optional[CancelToken] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> CompositionAudioMuxResult:
        if not isinstance(audio, AudioSettings):
            raise TypeError("audio must be AudioSettings")
        if on_progress is not None and not callable(on_progress):
            raise TypeError("on_progress must be callable")
        silent_video, narration_wav = Path(silent_video), Path(narration_wav)
        target = Path(destination).expanduser()
        if target.suffix.lower() != ".mp4":
            raise CompositionAudioMuxError("final video destination must use the .mp4 extension")
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise CompositionAudioMuxError("final video destination must be a regular file, not a symlink")
        if not silent_video.is_file() or not narration_wav.is_file():
            raise CompositionAudioMuxError("silent video and aligned narration WAV must both exist")
        duration_ticks, duration_s = composition_video_duration(plan)
        if not plan.slots:
            raise CompositionAudioMuxError("composition timeline has no scene slots")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise CompositionAudioMuxError("final video already exists; refusing to overwrite it")
        _cancel(cancel)
        _validate_silent_video(self._ffmpeg, silent_video, plan, cancel)
        narration_info = self._ffmpeg.probe(narration_wav, cancel=cancel)
        if not narration_info.has_audio or narration_info.duration_s is None:
            raise CompositionAudioMuxError("narration WAV has no readable audio stream")
        if narration_info.duration_s < duration_s - (1.0 / constants.VIDEO_AUDIO_SAMPLE_RATE):
            raise CompositionAudioMuxError("aligned narration WAV is shorter than the frame-quantized video timeline")

        mixed = has_mixing_work(audio)
        mixed_path = target.with_name(f".{target.stem}.voxora-mix.wav")
        part_path = target.with_name(target.name + ".part")
        if mixed_path.exists() or part_path.exists():
            raise CompositionAudioMuxError("a temporary output path already exists; refusing to overwrite it")
        try:
            audio_path = narration_wav
            if mixed:
                durations = dict(track_durations) if track_durations is not None else probe_track_durations(self._ffmpeg, audio)
                mix_args = build_composition_audio_mix_args(
                    self._ffmpeg.require(), narration_wav, plan, audio, durations, mixed_path,
                )
                if on_progress:
                    on_progress(0.0, "Mixing narration and music")
                self._ffmpeg.run_with_progress(
                    mix_args, duration_s,
                    lambda fraction: on_progress(0.4 * fraction, "Mixing narration and music") if on_progress else None,
                    cancel,
                )
                if not mixed_path.is_file() or mixed_path.stat().st_size <= 0:
                    raise CompositionAudioMuxError("existing Studio audio mixer did not produce a WAV file")
                audio_path = mixed_path

            _cancel(cancel)
            mux_args = build_composition_video_mux_args(
                self._ffmpeg.require(), silent_video, audio_path, plan, part_path,
            )
            if on_progress:
                on_progress(0.4 if mixed else 0.0, "Muxing final MP4")
            self._ffmpeg.run_with_progress(
                mux_args, duration_s,
                lambda fraction: on_progress((0.4 if mixed else 0.0) + (0.5 if mixed else 0.9) * fraction,
                                             "Muxing final MP4") if on_progress else None,
                cancel,
            )
            _cancel(cancel)
            if not part_path.is_file() or part_path.stat().st_size <= 0:
                raise CompositionAudioMuxError("FFmpeg did not produce the final MP4")
            video_codec, audio_codec = _validate_final_mp4(self._ffmpeg, part_path, plan, duration_s, cancel)
            _cancel(cancel)
            try:
                os.link(part_path, target)
            except FileExistsError:
                raise CompositionAudioMuxError(
                    "final video appeared during export; refusing to overwrite it"
                ) from None
            part_path.unlink()
            if on_progress:
                on_progress(1.0, "Final MP4 ready")
            return CompositionAudioMuxResult(
                destination=target, duration_ticks=duration_ticks,
                duration_seconds=duration_s, frame_count=plan.total_frames,
                mixed_audio=mixed, video_codec=video_codec, audio_codec=audio_codec,
            )
        except BaseException:
            part_path.unlink(missing_ok=True)
            raise
        finally:
            mixed_path.unlink(missing_ok=True)
