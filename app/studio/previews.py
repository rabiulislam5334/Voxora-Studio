from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from app.audio.ffmpeg_tool import FFmpegTool
from app.audio.mixer import build_mix_args, build_waveform_args
from app.cache.video_cache import VideoCache
from app.core.constants import EXPORT_AUDIO_SAMPLE_RATE
from app.core.exceptions import FFmpegError, MediaError, ProductionError
from app.studio.models import AudioSettings
from app.video.render import build_thumbnail_args
from app.workers.cancel import CancelToken


def make_thumbnail(ffmpeg: FFmpegTool, cache: VideoCache, source: Path, width: int = 320) -> Path:
    """PNG thumbnail of an image or the first frame of a video, cached by the
    file's identity. Blocking; call from a worker thread."""
    dest = cache.image_path("thumb", source, width)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    exe = ffmpeg.require()
    part = dest.with_name(dest.name + ".part")
    args = build_thumbnail_args(exe, source, part, width)
    args = args[:-1] + ["-f", "image2", str(part)]
    try:
        ffmpeg.run_args(args, timeout=60)
        part.replace(dest)
    except FFmpegError as exc:
        part.unlink(missing_ok=True)
        raise MediaError(f"Could not create a preview for '{Path(source).name}': {exc}") from exc
    return dest


def make_waveform(ffmpeg: FFmpegTool, cache: VideoCache, source: Path, width: int, height: int, color: str = "0x4aa3ff") -> Path:
    """Waveform PNG for an audio file, drawn by FFmpeg and cached."""
    dest = cache.image_path("wave", source, width, height, color)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    exe = ffmpeg.require()
    part = dest.with_name(dest.name + ".part")
    args = build_waveform_args(exe, source, part, width, height, color)
    args = args[:-1] + ["-f", "image2", str(part)]
    try:
        ffmpeg.run_args(args, timeout=300)
        part.replace(dest)
    except FFmpegError as exc:
        part.unlink(missing_ok=True)
        raise MediaError(f"Could not draw the waveform for '{Path(source).name}': {exc}") from exc
    return dest


def probe_track_durations(ffmpeg: FFmpegTool, audio: AudioSettings) -> Dict[str, float]:
    durations: Dict[str, float] = {}
    for track in audio.active_tracks():
        try:
            info = ffmpeg.probe(Path(track.path))
        except MediaError as exc:
            raise ProductionError(f"Music '{Path(track.path).name}': {exc}") from exc
        if not info.has_audio or not info.duration_s:
            raise ProductionError(f"Music '{Path(track.path).name}' has no readable audio.")
        durations[track.id] = info.duration_s
    return durations


def render_mix_preview(
    ffmpeg: FFmpegTool,
    narration_wav: Path,
    narration_total_s: float,
    audio: AudioSettings,
    dest: Path,
    seconds: float = 30.0,
    cancel: Optional[CancelToken] = None,
) -> Path:
    """Render only the first `seconds` of the mix to a WAV for quick listening.
    Same filter graph as the final export, so what you hear is what you get."""
    exe = ffmpeg.require()
    durations = probe_track_durations(ffmpeg, audio)
    args = build_mix_args(
        exe, narration_wav, narration_total_s, audio, durations, dest,
        fmt="wav", sample_rate=EXPORT_AUDIO_SAMPLE_RATE, max_seconds=seconds,
    )
    ffmpeg.run_args(args, cancel=cancel, timeout=300)
    return dest