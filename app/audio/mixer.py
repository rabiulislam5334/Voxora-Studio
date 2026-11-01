from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from app.core.exceptions import ProductionError
from app.studio.models import AudioSettings, MusicTrack

_FORMATS = {
    "wav": ["-c:a", "pcm_s16le", "-f", "wav"],
    "mp3": ["-c:a", "libmp3lame", "-f", "mp3"],
    "aac": ["-c:a", "aac", "-f", "adts"],
}


def _fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _music_chain(index: int, track: MusicTrack, duration_s: float, total_s: float, sample_rate: int) -> str:
    """Filter chain for one music input. All times are on the FINAL timeline."""
    start = track.trim_start_s
    end = track.trim_end_s if track.trim_end_s is not None else duration_s
    end = min(end, duration_s)
    if end <= start:
        raise ProductionError(f"Music '{Path(track.path).name}': trim range is outside the file.")
    clip_len = end - start
    available = max(0.0, total_s - track.offset_s)  # how long the music may play
    if available <= 0:
        raise ProductionError(f"Music '{Path(track.path).name}' starts after the narration ends.")

    parts = [
        f"aresample={sample_rate}",
        "aformat=channel_layouts=stereo",
        f"atrim=start={_fmt(start)}:end={_fmt(end)}",
        "asetpts=PTS-STARTPTS",
    ]
    if track.loop and clip_len < available:
        parts.append(f"aloop=loop=-1:size={int(clip_len * sample_rate) + 1}")
    parts.append(f"atrim=duration={_fmt(available)}")
    parts.append("asetpts=PTS-STARTPTS")
    parts.append(f"volume={track.volume_percent / 100:.4f}")
    play_len = min(available, clip_len if not track.loop else available)
    fade_in = min(track.fade_in_s, play_len / 2)
    fade_out = min(track.fade_out_s, play_len / 2)
    if fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={_fmt(fade_in)}")
    if fade_out > 0:
        parts.append(f"afade=t=out:st={_fmt(play_len - fade_out)}:d={_fmt(fade_out)}")
    if track.offset_s > 0:
        delay = int(round(track.offset_s * 1000))
        parts.append(f"adelay={delay}|{delay}")
    return f"[{index}:a]" + ",".join(parts) + f"[m{index}]"


def build_mix_args(
    ffmpeg_exe: Path,
    narration: Path,
    total_s: float,
    audio: AudioSettings,
    track_durations: Dict[str, float],
    dest: Path,
    *,
    fmt: str,
    sample_rate: int,
    mp3_bitrate: str = "192k",
    max_seconds: Optional[float] = None,
) -> List[str]:
    """Argument list that mixes the narration with the enabled music tracks.

    * narration timing is the reference: music is cut to its length;
    * `amix normalize=0` keeps levels exactly as set (no automatic gain);
    * an optional limiter keeps the sum below full scale (no clipping);
    * `max_seconds` renders only the first N seconds (fast mix preview)."""
    if fmt not in _FORMATS:
        raise ProductionError(f"Unsupported audio format: {fmt}")
    tracks = audio.active_tracks()
    cmd: List[str] = [str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(narration)]
    filters = [
        f"[0:a]aresample={sample_rate},aformat=channel_layouts=stereo,"
        f"volume={audio.narration_volume_percent / 100:.4f}[n]"
    ]
    labels = ["[n]"]
    for i, track in enumerate(tracks, start=1):
        if track.id not in track_durations:
            raise ProductionError(f"Music '{Path(track.path).name}' could not be read.")
        cmd += ["-i", str(track.path)]
        filters.append(_music_chain(i, track, track_durations[track.id], total_s, sample_rate))
        labels.append(f"[m{i}]")

    if len(labels) > 1:
        filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest:dropout_transition=0[mix]")
        last = "[mix]"
    else:
        last = "[n]"
    tail = []
    if audio.limiter:
        tail.append("alimiter=limit=0.95:level=0")
    tail.append(f"atrim=duration={_fmt(total_s if max_seconds is None else min(total_s, max_seconds))}")
    filters.append(f"{last}{','.join(tail)}[out]")

    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", str(sample_rate), "-ac", "2"]
    cmd += _FORMATS[fmt]
    if fmt == "mp3":
        cmd += ["-b:a", mp3_bitrate]
    cmd.append(str(dest))
    return cmd


def build_waveform_args(ffmpeg_exe: Path, source: Path, dest_png: Path, width: int, height: int, color: str) -> List[str]:
    """One PNG of the whole file's waveform, drawn by FFmpeg itself (no
    Python sample loops, so even hour-long files are quick)."""
    return [
        str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
        "-filter_complex", f"aformat=channel_layouts=mono,showwavespic=s={width}x{height}:colors={color}",
        "-frames:v", "1", "-c:v", "png", str(dest_png),
    ]


def has_mixing_work(audio: AudioSettings) -> bool:
    return bool(audio.active_tracks()) or audio.narration_volume_percent != 100