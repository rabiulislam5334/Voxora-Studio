from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from app.core import constants

_ZOOM = 0.15  # total zoom travel for zoom_in / zoom_out / pan (15%)
_SUPERSAMPLE = 1.5  # zoompan works on a larger frame to avoid visible jitter


@dataclass(frozen=True)
class SegmentSpec:
    kind: str                 # "image" | "video" | "blank"
    media: Optional[str]
    length_s: float
    width: int
    height: int
    fps: int
    motion: str = "none"
    fit: str = "fill"

    @property
    def frames(self) -> int:
        return max(1, int(round(self.length_s * self.fps)))


def _even(value: float) -> int:
    return max(2, int(round(value / 2)) * 2)


def _fit_filter(width: int, height: int, fit: str) -> str:
    if fit == "fit":
        return (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black")
    return f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"


def _zoompan(spec: SegmentSpec) -> str:
    n = spec.frames
    denominator = max(1, n - 1)
    base = f"d={n}:s={spec.width}x{spec.height}:fps={spec.fps}"
    center_y = "y='ih/2-ih/zoom/2'"
    if spec.motion == "zoom_out":
        z = f"z='{1 + _ZOOM}-{_ZOOM}*on/{denominator}'"
        pos = f"x='iw/2-iw/zoom/2':{center_y}"
    elif spec.motion == "pan_left":
        z = f"z='{1 + _ZOOM}'"
        pos = f"x='(iw-iw/zoom)*(1-on/{denominator})':{center_y}"
    elif spec.motion == "pan_right":
        z = f"z='{1 + _ZOOM}'"
        pos = f"x='(iw-iw/zoom)*on/{denominator}':{center_y}"
    else:  # zoom_in
        z = f"z='1+{_ZOOM}*on/{denominator}'"
        pos = f"x='iw/2-iw/zoom/2':{center_y}"
    return f"zoompan={z}:{pos}:{base}"


def _encode_args(fps: int) -> List[str]:
    return [
        "-c:v", "libx264", "-preset", constants.VIDEO_PRESET, "-crf", str(constants.VIDEO_CRF),
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", str(fps * 2), "-an",
    ]


def build_segment_args(ffmpeg_exe: Path, spec: SegmentSpec, dest: Path) -> List[str]:
    """One silent H.264 segment of exactly spec.length_s: a still image
    (optionally with zoom/pan), a looped/trimmed video clip, or black."""
    base = [str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    out = ["-r", str(spec.fps), *_encode_args(spec.fps), "-f", "mp4", str(dest)]
    w, h = spec.width, spec.height

    if spec.kind == "blank" or not spec.media:
        return base + ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={spec.fps}",
                       "-t", f"{spec.length_s:.3f}", "-vf", "setsar=1", *out]

    if spec.kind == "video":
        vf = f"fps={spec.fps},{_fit_filter(w, h, spec.fit)},setsar=1,format=yuv420p"
        return base + ["-stream_loop", "-1", "-i", spec.media, "-t", f"{spec.length_s:.3f}", "-vf", vf, *out]

    # image
    if spec.motion == "none":
        # Scale the picture ONCE and repeat it (zoompan with a fixed zoom).
        # `-loop 1` would re-scale a possibly huge photo for every frame.
        vf = (f"{_fit_filter(w, h, spec.fit)},setsar=1,"
              f"zoompan=z='1':x=0:y=0:d={spec.frames}:s={w}x{h}:fps={spec.fps},setsar=1,format=yuv420p")
        return base + ["-i", spec.media, "-vf", vf, "-frames:v", str(spec.frames), *out]
    big_w, big_h = _even(w * _SUPERSAMPLE), _even(h * _SUPERSAMPLE)
    vf = f"{_fit_filter(big_w, big_h, spec.fit)},setsar=1,{_zoompan(spec)},setsar=1,format=yuv420p"
    return base + ["-i", spec.media, "-vf", vf, "-frames:v", str(spec.frames), *out]


# ----------------------------------------------------------------------
# Joining and muxing
# ----------------------------------------------------------------------


def build_concat_list(paths: Sequence[Path]) -> str:
    """Text for FFmpeg's concat demuxer. Forward slashes and escaped quotes
    keep Windows paths (spaces, Bengali names, apostrophes) intact."""
    lines = []
    for path in paths:
        text = str(Path(path).resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{text}'")
    return "\n".join(lines) + "\n"


def build_cut_join_args(ffmpeg_exe: Path, list_file: Path, dest: Path) -> List[str]:
    return [str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", "-f", "mp4", str(dest)]


def build_xfade_script(starts: Sequence[float], transition_s: float) -> str:
    """filter_complex script chaining `xfade` across N segment inputs.
    starts[i] is the timeline position where scene i begins; the fade into
    scene i runs during [starts[i], starts[i] + transition_s]."""
    n = len(starts)
    if n < 2:
        return "[0:v]format=yuv420p[vout]"
    chain = []
    previous = "[0:v]"
    for i in range(1, n):
        label = "[vout]" if i == n - 1 else f"[v{i}]"
        chain.append(
            f"{previous}[{i}:v]xfade=transition=fade:duration={transition_s:.3f}:offset={starts[i]:.3f}{label}"
        )
        previous = label
    return ";".join(chain)


# How to hand FFmpeg a filter graph stored in a file. FFmpeg 7+ spells it
# `-/filter_complex <file>`; the old `-filter_complex_script <file>` was
# deprecated in 7 and REMOVED in later releases (e.g. 9.x), but is the only
# form FFmpeg 6 and older understand. The caller tries them in this order.
FILTER_SCRIPT_OPTIONS = ("-/filter_complex", "-filter_complex_script")


def build_xfade_join_args(
    ffmpeg_exe: Path, segments: Sequence[Path], script_file: Path, fps: int, dest: Path,
    script_option: str = FILTER_SCRIPT_OPTIONS[0],
) -> List[str]:
    cmd = [str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for seg in segments:
        cmd += ["-i", str(seg)]
    cmd += [script_option, str(script_file), "-map", "[vout]", "-r", str(fps),
            *_encode_args(fps), "-f", "mp4", str(dest)]
    return cmd


def is_unknown_option_error(message: str) -> bool:
    """True when FFmpeg rejected an option it does not know (old/new FFmpeg mismatch)."""
    text = message.lower()
    return "option not found" in text or "unrecognized option" in text


def build_mux_args(ffmpeg_exe: Path, video: Path, audio: Path, total_s: float, dest: Path) -> List[str]:
    """Combine the joined video and the mixed audio: video is copied (no
    quality loss, no re-encode), audio becomes AAC at a fixed sample rate."""
    return [
        str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", constants.VIDEO_AUDIO_BITRATE,
        "-ar", str(constants.VIDEO_AUDIO_SAMPLE_RATE), "-ac", "2",
        "-t", f"{total_s:.3f}", "-movflags", "+faststart", "-f", "mp4", str(dest),
    ]


def build_thumbnail_args(ffmpeg_exe: Path, source: Path, dest_png: Path, width: int = 320) -> List[str]:
    return [str(ffmpeg_exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
            "-frames:v", "1", "-vf", f"scale={width}:-2", "-c:v", "png", str(dest_png)]