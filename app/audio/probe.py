from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.core.exceptions import MediaError

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VIDEO_RE = re.compile(r"Stream #\d+:\d+[^:]*:\s*Video:(?P<rest>.*)")
_SIZE_RE = re.compile(r",\s*(\d{2,5})x(\d{2,5})")
_AUDIO_RE = re.compile(r"Stream #\d+:\d+[^:]*:\s*Audio:")
_INPUT_RE = re.compile(r"Input #0,\s*([\w,]+)")
_STILL_FORMATS = {"image2", "image2pipe", "png_pipe", "jpeg_pipe", "webp_pipe", "bmp_pipe", "tiff_pipe"}


@dataclass(frozen=True)
class MediaInfo:
    duration_s: Optional[float]
    has_video: bool
    has_audio: bool
    width: Optional[int]
    height: Optional[int]
    is_image: bool

    @property
    def kind(self) -> str:
        if self.is_image:
            return "image"
        if self.has_video:
            return "video"
        if self.has_audio:
            return "audio"
        return "unknown"


@dataclass(frozen=True)
class StreamInfo:
    """Structured metadata for one FFprobe stream; absent values remain None."""

    index: Optional[int]
    codec_type: Optional[str]
    codec_name: Optional[str]
    duration_s: Optional[float]
    start_time_s: Optional[float]
    time_base: Optional[str]
    avg_frame_rate: Optional[str]
    real_frame_rate: Optional[str]
    width: Optional[int]
    height: Optional[int]
    sample_rate: Optional[int]
    channels: Optional[int]
    decoded_frame_count: Optional[int] = None


@dataclass(frozen=True)
class FrameTimestampInfo:
    """Summary of decoded video presentation timestamps."""

    frame_count: int
    missing_timestamp_count: int
    non_monotonic_count: int
    cfr_interval_mismatch_count: int
    first_timestamp_s: Optional[float]
    last_timestamp_s: Optional[float]


@dataclass(frozen=True)
class StructuredMediaInfo:
    """Container and stream metadata returned by FFprobe."""

    format_name: Optional[str]
    format_duration_s: Optional[float]
    format_start_time_s: Optional[float]
    streams: tuple[StreamInfo, ...]


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value and value != "N/A" else None


def parse_ffprobe_json(payload: str) -> StructuredMediaInfo:
    """Parse FFprobe JSON without inventing values for missing metadata."""
    try:
        document = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MediaError(f"FFprobe returned invalid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise MediaError("FFprobe returned an unexpected JSON document.")
    raw_streams = document.get("streams", [])
    if not isinstance(raw_streams, list):
        raise MediaError("FFprobe returned an invalid streams collection.")

    streams: list[StreamInfo] = []
    for raw in raw_streams:
        if not isinstance(raw, dict):
            raise MediaError("FFprobe returned an invalid stream entry.")
        streams.append(StreamInfo(
            index=_optional_int(raw.get("index")),
            codec_type=_optional_text(raw.get("codec_type")),
            codec_name=_optional_text(raw.get("codec_name")),
            duration_s=_optional_float(raw.get("duration")),
            start_time_s=_optional_float(raw.get("start_time")),
            time_base=_optional_text(raw.get("time_base")),
            avg_frame_rate=_optional_text(raw.get("avg_frame_rate")),
            real_frame_rate=_optional_text(raw.get("r_frame_rate")),
            width=_optional_int(raw.get("width")),
            height=_optional_int(raw.get("height")),
            sample_rate=_optional_int(raw.get("sample_rate")),
            channels=_optional_int(raw.get("channels")),
            decoded_frame_count=_optional_int(raw.get("nb_read_frames")),
        ))

    raw_format = document.get("format", {})
    if raw_format is None:
        raw_format = {}
    if not isinstance(raw_format, dict):
        raise MediaError("FFprobe returned invalid format metadata.")
    return StructuredMediaInfo(
        format_name=_optional_text(raw_format.get("format_name")),
        format_duration_s=_optional_float(raw_format.get("duration")),
        format_start_time_s=_optional_float(raw_format.get("start_time")),
        streams=tuple(streams),
    )


def parse_frame_timestamp_output(output: str, expected_fps: int) -> FrameTimestampInfo:
    """Summarize one decoded video timestamp per line and verify CFR spacing."""
    if expected_fps <= 0:
        raise ValueError("expected_fps must be positive")

    # JSON preserves one object per decoded frame. The default/keyless
    # writer can emit additional side-data lines (for example H.264 SEI),
    # which must never be counted as frames.
    try:
        document = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        document = None

    if isinstance(document, dict) and isinstance(document.get("frames"), list):
        timestamps = [
            _optional_float(frame.get("best_effort_timestamp_time"))
            if isinstance(frame, dict) else None
            for frame in document["frames"]
        ]
    else:
        raw_values = [line.strip().split(",", 1)[0].strip()
                      for line in output.splitlines() if line.strip()]
        timestamps = [_optional_float(value) for value in raw_values]
    expected_interval = 1.0 / expected_fps
    # FFprobe's default timestamp formatting is microsecond precision.
    tolerance = max(2e-6, expected_interval * 1e-5)
    non_monotonic = 0
    cfr_mismatches = 0
    previous: Optional[float] = None
    for current in timestamps:
        if previous is not None and current is not None:
            interval = current - previous
            if interval <= 0:
                non_monotonic += 1
            elif abs(interval - expected_interval) > tolerance:
                cfr_mismatches += 1
        previous = current

    valid = [value for value in timestamps if value is not None]
    return FrameTimestampInfo(
        frame_count=len(timestamps),
        missing_timestamp_count=len(timestamps) - len(valid),
        non_monotonic_count=non_monotonic,
        cfr_interval_mismatch_count=cfr_mismatches,
        first_timestamp_s=valid[0] if valid else None,
        last_timestamp_s=valid[-1] if valid else None,
    )



def parse_frame_timestamp_json(payload: str, expected_fps: int) -> FrameTimestampInfo:
    """Parse FFprobe's frame JSON so nested side-data records cannot look like frames."""
    if expected_fps <= 0:
        raise ValueError("expected_fps must be positive")
    try:
        document = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MediaError(f"FFprobe returned invalid frame JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("frames"), list):
        raise MediaError("FFprobe returned an invalid frame collection.")

    timestamps: list[Optional[float]] = []
    for frame in document["frames"]:
        if not isinstance(frame, dict):
            raise MediaError("FFprobe returned an invalid frame entry.")
        timestamps.append(_optional_float(frame.get("best_effort_timestamp_time")))

    expected_interval = 1.0 / expected_fps
    tolerance = max(2e-6, expected_interval * 1e-5)
    non_monotonic = 0
    cfr_mismatches = 0
    previous: Optional[float] = None
    for current in timestamps:
        if previous is not None and current is not None:
            interval = current - previous
            if interval <= 0:
                non_monotonic += 1
            elif abs(interval - expected_interval) > tolerance:
                cfr_mismatches += 1
        previous = current

    valid = [value for value in timestamps if value is not None]
    return FrameTimestampInfo(
        frame_count=len(timestamps),
        missing_timestamp_count=len(timestamps) - len(valid),
        non_monotonic_count=non_monotonic,
        cfr_interval_mismatch_count=cfr_mismatches,
        first_timestamp_s=valid[0] if valid else None,
        last_timestamp_s=valid[-1] if valid else None,
    )

def parse_probe_output(stderr_text: str) -> MediaInfo:
    """Parse the FFmpeg input banner (no FFprobe needed).
    Raises MediaError when the output does not describe a media file."""
    if "Input #0" not in stderr_text:
        reason = "not a readable media file"
        for line in stderr_text.splitlines():
            if "No such file" in line or "Invalid data" in line or "Permission denied" in line:
                reason = line.strip().split(": ", 1)[-1]
                break
        raise MediaError(f"Cannot read media: {reason}.")

    duration: Optional[float] = None
    match = _DURATION_RE.search(stderr_text)
    if match:
        h, m, s = match.groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s)

    width = height = None
    has_video = False
    for line in stderr_text.splitlines():
        vm = _VIDEO_RE.search(line)
        if vm and "attached pic" not in line:
            has_video = True
            sm = _SIZE_RE.search(vm.group("rest"))
            if sm and width is None:
                width, height = int(sm.group(1)), int(sm.group(2))

    if has_video and width is None:
        raise MediaError("Cannot read media: the picture data is invalid or unsupported.")

    input_match = _INPUT_RE.search(stderr_text)
    formats = set((input_match.group(1) if input_match else "").split(","))
    is_image = has_video and bool(formats & _STILL_FORMATS)
    return MediaInfo(
        duration_s=None if is_image else duration,
        has_video=has_video,
        has_audio=bool(_AUDIO_RE.search(stderr_text)),
        width=width,
        height=height,
        is_image=is_image,
    )
