from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

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


def parse_probe_output(stderr_text: str) -> MediaInfo:
    """Parse the banner `ffmpeg -i <file>` prints (no ffprobe needed).
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