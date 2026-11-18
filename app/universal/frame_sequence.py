"""Validated numbered PNG sequences and a CPU FFmpeg MP4 encoding bridge.

The encoder consumes frames produced elsewhere. It does not animate scenes,
render artwork, mux audio, or modify project state.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence


class FrameSequenceError(RuntimeError):
    """Base error for invalid frame sequences and encoding failures."""


class FrameSequenceCancelledError(FrameSequenceError):
    """Raised when encoding is cancelled; the final destination is untouched."""


@dataclass(frozen=True)
class FrameSequenceLimits:
    max_frames: int = 100_000
    max_width: int = 4096
    max_height: int = 4096
    max_canvas_pixels: int = 8_388_608
    max_frame_bytes: int = 100 * 1024 * 1024
    max_total_bytes: int = 2 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_frames", "max_width", "max_height", "max_canvas_pixels",
            "max_frame_bytes", "max_total_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class FrameSequence:
    """A contiguous, numerically named PNG sequence at a constant frame rate."""

    frame_paths: tuple[Path, ...]
    fps: int

    def __post_init__(self) -> None:
        if isinstance(self.frame_paths, (str, bytes)):
            raise ValueError("frame_paths must be a sequence of paths")
        try:
            paths = tuple(Path(item) for item in self.frame_paths)
        except (TypeError, ValueError):
            raise ValueError("frame_paths must contain valid paths") from None
        if not paths:
            raise ValueError("frame sequence must contain at least one frame")
        if isinstance(self.fps, bool) or not isinstance(self.fps, int) or not 1 <= self.fps <= 120:
            raise ValueError("fps must be an integer between 1 and 120")
        if len(paths) > 100_000:
            raise ValueError("frame sequence exceeds the hard frame-count limit")

        first = paths[0]
        match = re.fullmatch(r"(.*?)(\d+)\.png", first.name, flags=re.IGNORECASE)
        if match is None:
            raise ValueError("frame names must use a shared prefix and numeric .png suffix")
        prefix, number = match.groups()
        width = len(number)
        start = int(number)
        parent = first.parent
        for index, path in enumerate(paths):
            current = re.fullmatch(r"(.*?)(\d+)\.png", path.name, flags=re.IGNORECASE)
            if (
                path.parent != parent
                or current is None
                or current.group(1) != prefix
                or len(current.group(2)) != width
                or int(current.group(2)) != start + index
                or path.suffix.lower() != ".png"
            ):
                raise ValueError("frame paths must be contiguous PNG files with one prefix and index width")
        object.__setattr__(self, "frame_paths", paths)

    @classmethod
    def from_paths(cls, frame_paths: Sequence[os.PathLike[str] | str], *, fps: int) -> "FrameSequence":
        return cls(tuple(Path(path) for path in frame_paths), fps)

    @property
    def frame_count(self) -> int:
        return len(self.frame_paths)

    @property
    def start_number(self) -> int:
        match = re.fullmatch(r".*?(\d+)\.png", self.frame_paths[0].name, flags=re.IGNORECASE)
        assert match is not None
        return int(match.group(1))

    @property
    def input_pattern(self) -> Path:
        first = self.frame_paths[0]
        match = re.fullmatch(r"(.*?)(\d+)\.png", first.name, flags=re.IGNORECASE)
        assert match is not None
        prefix, number = match.groups()
        return first.with_name(f"{prefix}%0{len(number)}d.png")


@dataclass(frozen=True)
class FrameSequenceEncodeResult:
    destination: Path
    frame_count: int
    fps: int
    width: int
    height: int
    duration_seconds: float
    output_sha256: str
    codec: str = "h264"


def build_frame_sequence_encode_args(
    ffmpeg_executable: os.PathLike[str] | str,
    sequence: FrameSequence,
    destination: os.PathLike[str] | str,
) -> list[str]:
    """Build a deterministic silent H.264 MP4 command for a numbered PNG sequence."""
    if not isinstance(sequence, FrameSequence):
        raise TypeError("sequence must be a FrameSequence")
    return [
        str(ffmpeg_executable), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-y", "-framerate", str(sequence.fps),
        "-start_number", str(sequence.start_number),
        "-i", str(sequence.input_pattern),
        "-frames:v", str(sequence.frame_count),
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", "-f", "mp4", str(destination),
    ]


def _is_cancelled(cancel) -> bool:
    if cancel is None:
        return False
    if isinstance(cancel, bool):
        return cancel
    value = getattr(cancel, "cancelled", None)
    if value is not None:
        return bool(value)
    is_set = getattr(cancel, "is_set", None)
    if callable(is_set):
        return bool(is_set())
    if callable(cancel):
        return bool(cancel())
    raise FrameSequenceError("cancel must be a boolean, callable, or event-like object")


def _resolve_executable(value: os.PathLike[str] | str, name: str) -> str:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise FrameSequenceError(f"{name} executable must be a non-empty path or command")
    raw = str(value)
    candidate = Path(raw).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        if candidate.is_symlink() or not candidate.is_file():
            raise FrameSequenceError(f"{name} executable is not a regular file")
        return str(candidate.resolve(strict=True))
    resolved = shutil.which(raw)
    if not resolved:
        raise FrameSequenceError(f"{name} executable was not found: {raw}")
    return resolved


def _inspect_sequence(sequence: FrameSequence, limits: FrameSequenceLimits) -> tuple[int, int]:
    if sequence.frame_count > limits.max_frames:
        raise FrameSequenceError("frame sequence exceeds the configured frame-count limit")
    total_bytes = 0
    dimensions: Optional[tuple[int, int]] = None
    try:
        from PIL import Image
        for path in sequence.frame_paths:
            if path.is_symlink():
                raise FrameSequenceError("symbolic-link frame paths are not accepted")
            resolved = path.resolve(strict=True)
            if not resolved.is_file():
                raise FrameSequenceError("every frame must be a regular file")
            size = resolved.stat().st_size
            if size <= 0 or size > limits.max_frame_bytes:
                raise FrameSequenceError("frame is empty or exceeds the configured byte limit")
            total_bytes += size
            if total_bytes > limits.max_total_bytes:
                raise FrameSequenceError("frame sequence exceeds the configured total byte limit")
            with Image.open(resolved) as image:
                if image.format != "PNG":
                    raise FrameSequenceError("all frame files must contain valid PNG images")
                width, height = image.size
                if width <= 0 or height <= 0:
                    raise FrameSequenceError("frame dimensions must be positive")
                if width > limits.max_width or height > limits.max_height:
                    raise FrameSequenceError("frame dimensions exceed the configured limits")
                if width * height > limits.max_canvas_pixels:
                    raise FrameSequenceError("frame pixel count exceeds the configured limit")
                image.verify()
            if dimensions is None:
                dimensions = (width, height)
                if width % 2 or height % 2:
                    raise FrameSequenceError("H.264 yuv420p output requires even frame dimensions")
            elif dimensions != (width, height):
                raise FrameSequenceError("all frames must have identical dimensions")
    except FrameSequenceError:
        raise
    except Exception as exc:
        raise FrameSequenceError(f"cannot inspect frame sequence: {exc}") from exc
    assert dimensions is not None
    return dimensions


def _run_ffmpeg(
    args: list[str],
    *,
    frame_count: int,
    on_progress: Optional[Callable[[float], None]],
    cancel,
) -> None:
    try:
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
    except OSError as exc:
        raise FrameSequenceError(f"could not start FFmpeg: {exc}") from exc

    events: queue.Queue[tuple[str, Optional[str]]] = queue.Queue()
    stderr_tail: list[str] = []

    def drain(stream, label: str) -> None:
        try:
            for line in iter(stream.readline, ""):
                events.put((label, line.rstrip("\r\n")))
        finally:
            events.put((label, None))
            stream.close()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True),
    ]
    for reader in readers:
        reader.start()

    completed_streams = set()
    last_progress = -1.0
    try:
        while process.poll() is None or len(completed_streams) < 2:
            if _is_cancelled(cancel):
                process.kill()
                process.wait()
                raise FrameSequenceCancelledError("FFmpeg frame-sequence encoding was cancelled")
            try:
                label, line = events.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                completed_streams.add(label)
                continue
            if label == "stderr":
                stderr_tail.append(line)
                if len(stderr_tail) > 80:
                    del stderr_tail[: len(stderr_tail) - 80]
            elif line.startswith("frame="):
                try:
                    frame = int(line.partition("=")[2].strip())
                    progress = min(1.0, max(0.0, frame / frame_count))
                    if progress > last_progress:
                        last_progress = progress
                        if on_progress:
                            on_progress(progress)
                except ValueError:
                    pass
        return_code = process.wait()
        if return_code != 0:
            detail = "\n".join(stderr_tail).strip() or f"FFmpeg exited with code {return_code}"
            raise FrameSequenceError(detail[-8000:])
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise
    finally:
        for reader in readers:
            reader.join(timeout=1)


class FFmpegFrameSequenceEncoder:
    """Encode validated numbered PNG frames to a silent H.264 MP4 artifact."""

    def __init__(
        self,
        ffmpeg_executable: os.PathLike[str] | str = "ffmpeg",
        *,
        ffprobe_executable: os.PathLike[str] | str | None = None,
        limits: Optional[FrameSequenceLimits] = None,
    ) -> None:
        self.ffmpeg_executable = _resolve_executable(ffmpeg_executable, "FFmpeg")
        if ffprobe_executable is None:
            sibling = Path(self.ffmpeg_executable).with_name(
                "ffprobe.exe" if os.name == "nt" else "ffprobe"
            )
            self.ffprobe_executable = str(sibling) if sibling.is_file() else shutil.which("ffprobe")
        else:
            self.ffprobe_executable = _resolve_executable(ffprobe_executable, "FFprobe")
        self.limits = limits or FrameSequenceLimits()
        if not isinstance(self.limits, FrameSequenceLimits):
            raise TypeError("limits must be FrameSequenceLimits")

    def _verify_output(self, path: Path, sequence: FrameSequence, width: int, height: int) -> None:
        if not path.is_file() or path.stat().st_size <= 0:
            raise FrameSequenceError("FFmpeg produced a missing or empty MP4")
        if self.ffprobe_executable:
            args = [
                self.ffprobe_executable, "-v", "error", "-count_frames",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,nb_read_frames",
                "-of", "json", str(path),
            ]
            try:
                result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
                if result.returncode != 0:
                    raise FrameSequenceError(result.stderr.strip() or "FFprobe could not inspect MP4 output")
                streams = json.loads(result.stdout).get("streams", [])
                if not streams:
                    raise FrameSequenceError("MP4 output contains no video stream")
                stream = streams[0]
                if (
                    stream.get("codec_name") != "h264"
                    or int(stream.get("width", 0)) != width
                    or int(stream.get("height", 0)) != height
                    or int(stream.get("nb_read_frames", -1)) != sequence.frame_count
                ):
                    raise FrameSequenceError("MP4 output metadata does not match the requested frame sequence")
            except FrameSequenceError:
                raise
            except Exception as exc:
                raise FrameSequenceError(f"could not verify MP4 output: {exc}") from exc
        else:
            verify_args = [
                self.ffmpeg_executable, "-hide_banner", "-loglevel", "error",
                "-nostdin", "-i", str(path), "-f", "null", "-",
            ]
            try:
                result = subprocess.run(verify_args, capture_output=True, text=True, timeout=60, check=False)
            except Exception as exc:
                raise FrameSequenceError(f"could not decode-check MP4 output: {exc}") from exc
            if result.returncode != 0:
                raise FrameSequenceError(result.stderr.strip() or "MP4 output failed decode verification")

    def encode(
        self,
        sequence: FrameSequence,
        destination: os.PathLike[str] | str,
        *,
        overwrite: bool = False,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel=None,
    ) -> FrameSequenceEncodeResult:
        if not isinstance(sequence, FrameSequence):
            raise TypeError("sequence must be a FrameSequence")
        if not isinstance(overwrite, bool):
            raise FrameSequenceError("overwrite must be a boolean")
        if on_progress is not None and not callable(on_progress):
            raise FrameSequenceError("on_progress must be callable")
        if _is_cancelled(cancel):
            raise FrameSequenceCancelledError("FFmpeg frame-sequence encoding was cancelled")
        width, height = _inspect_sequence(sequence, self.limits)

        target = Path(destination).expanduser()
        if target.suffix.lower() != ".mp4":
            raise FrameSequenceError("frame-sequence output destination must use the .mp4 extension")
        if target.is_symlink():
            raise FrameSequenceError("output destination must not be a symbolic link")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and (not target.is_file() or not overwrite):
            raise FrameSequenceError("output exists or is not a regular file; explicit overwrite is required")

        fd, temp_name = tempfile.mkstemp(prefix=".voxora-frames-", suffix=".mp4", dir=str(target.parent))
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            args = build_frame_sequence_encode_args(
                self.ffmpeg_executable, sequence, temp_path,
            )
            if on_progress:
                on_progress(0.0)
            _run_ffmpeg(
                args, frame_count=sequence.frame_count,
                on_progress=on_progress, cancel=cancel,
            )
            if _is_cancelled(cancel):
                raise FrameSequenceCancelledError("FFmpeg frame-sequence encoding was cancelled")
            self._verify_output(temp_path, sequence, width, height)
            if overwrite:
                os.replace(temp_path, target)
            else:
                try:
                    os.link(temp_path, target)
                except FileExistsError:
                    raise FrameSequenceError("output appeared during encoding; refusing to overwrite it") from None
                temp_path.unlink()
            digest = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if on_progress:
                on_progress(1.0)
            return FrameSequenceEncodeResult(
                destination=target, frame_count=sequence.frame_count, fps=sequence.fps,
                width=width, height=height,
                duration_seconds=sequence.frame_count / sequence.fps,
                output_sha256=digest.hexdigest(),
            )
        except FrameSequenceError:
            raise
        except Exception as exc:
            raise FrameSequenceError(f"frame-sequence encoding failed: {exc}") from exc
        finally:
            temp_path.unlink(missing_ok=True)


class FFmpegFrameSequenceAdapter:
    """Small explicit adapter exposing the frame-sequence encoder capability."""

    engine_id = "ffmpeg-frame-sequence"

    def __init__(self, encoder: Optional[FFmpegFrameSequenceEncoder] = None) -> None:
        from app.universal.engines import EngineCapabilities, EngineDescriptor

        self.encoder = encoder or FFmpegFrameSequenceEncoder()
        self.descriptor = EngineDescriptor(
            engine_id=self.engine_id,
            display_name="FFmpeg PNG Frame Sequence Encoder",
            version="1.0.0",
            capabilities=EngineCapabilities(
                scene_kinds=("frame_sequence",), asset_kinds=("image_sequence",),
                output_formats=("mp4",), requires_gpu=False,
                supports_draft_render=True, max_concurrent_jobs=1,
                estimated_memory_mb=256,
            ),
        )

    def encode(
        self, sequence: FrameSequence, destination: os.PathLike[str] | str, *,
        overwrite: bool = False, on_progress=None, cancel=None,
    ) -> FrameSequenceEncodeResult:
        return self.encoder.encode(
            sequence, destination, overwrite=overwrite,
            on_progress=on_progress, cancel=cancel,
        )


BUILTIN_FRAME_SEQUENCE_ENCODER_IDS = ("ffmpeg-frame-sequence",)


def build_builtin_frame_sequence_encoder(
    encoder: Optional[FFmpegFrameSequenceEncoder] = None,
) -> dict[str, FFmpegFrameSequenceAdapter]:
    """Return the explicit built-in encoder registry; no probing or fallback."""
    adapter = FFmpegFrameSequenceAdapter(encoder)
    return {adapter.engine_id: adapter}
