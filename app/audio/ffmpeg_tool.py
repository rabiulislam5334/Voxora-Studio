from __future__ import annotations

import asyncio
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from app.audio.probe import (FrameTimestampInfo, MediaInfo, StructuredMediaInfo,
                             parse_ffprobe_json, parse_frame_timestamp_json, parse_probe_output)
from app.core.exceptions import FFmpegError, GenerationCancelled, MediaError
from app.core.logger import get_logger
from app.core.settings_store import SettingsStore
from app.workers.cancel import CancelToken

logger = get_logger("audio.ffmpeg")

SETTINGS_KEY = "ffmpeg_path"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_INSTALL_HINT = (
    "Install FFmpeg (for example: winget install --id Gyan.FFmpeg -e), restart the app, "
    "or choose ffmpeg.exe with 'Set Path...'."
)


@dataclass(frozen=True)
class FFmpegStatus:
    available: bool
    path: Optional[Path]
    version: Optional[str]
    source: str
    message: str


class FFmpegTool:
    """Locate, verify and run FFmpeg commands without invoking a shell."""

    def __init__(self, settings: SettingsStore) -> None:
        self._settings = settings
        self._status: Optional[FFmpegStatus] = None

    @property
    def status(self) -> Optional[FFmpegStatus]:
        return self._status

    def configured_path(self) -> Optional[str]:
        value = self._settings.get(SETTINGS_KEY)
        return value if isinstance(value, str) and value.strip() else None

    def set_configured_path(self, path: Optional[str]) -> None:
        self._settings.set(SETTINGS_KEY, path.strip() if path else None)
        self._status = None

    async def detect_async(self) -> FFmpegStatus:
        return await asyncio.to_thread(self.detect)

    def detect(self) -> FFmpegStatus:
        problems: List[str] = []
        for source, candidate in self._candidates():
            ok, version, reason = self._verify(candidate)
            if ok:
                self._status = FFmpegStatus(
                    True, candidate, version, source, f"FFmpeg ready ({version})."
                )
                logger.info("FFmpeg verified via %s: %s (%s)", source, candidate, version)
                return self._status
            problems.append(f"{candidate}: {reason}")
            logger.warning("FFmpeg candidate rejected (%s): %s -- %s", source, candidate, reason)

        detail = f" Checked: {'; '.join(problems)}." if problems else ""
        self._status = FFmpegStatus(
            False, None, None, "none",
            f"FFmpeg was not found or is not working.{detail} {_INSTALL_HINT}",
        )
        return self._status

    def require(self) -> Path:
        status = self._status
        if status is None or (status.available and status.path and not status.path.exists()):
            status = self.detect()
        if not status.available or status.path is None:
            raise FFmpegError(status.message)
        return status.path

    def _candidates(self):
        configured = self.configured_path()
        if configured:
            yield "settings", Path(configured)
        found = shutil.which("ffmpeg")
        if found:
            yield "path", Path(found)
        try:
            import imageio_ffmpeg  # type: ignore[import-not-found]
            yield "imageio", Path(imageio_ffmpeg.get_exe())
        except Exception:
            return

    def _verify(self, exe: Path):
        if not exe.is_file():
            return False, None, "file does not exist"
        try:
            result = self._run([str(exe), "-version"], timeout=15.0)
        except FFmpegError as exc:
            return False, None, str(exc)
        first_line = (result.splitlines() or [""])[0].strip()
        if not first_line.lower().startswith("ffmpeg version"):
            return False, None, "not an FFmpeg executable"
        try:
            encoders = self._run([str(exe), "-hide_banner", "-encoders"], timeout=15.0)
        except FFmpegError as exc:
            return False, None, str(exc)
        if "libmp3lame" not in encoders:
            return False, None, "this FFmpeg build has no MP3 encoder (libmp3lame)"
        return True, first_line.replace("ffmpeg version", "").strip().split(" ")[0] or first_line, ""

    def decode_to_wav(
        self, source: Path, dest: Path, sample_rate: int, cancel: Optional[CancelToken] = None
    ) -> None:
        exe = self.require()
        args = [
            str(exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(source), "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-c:a", "pcm_s16le", "-f", "wav", str(dest),
        ]
        self._run(args, cancel=cancel, timeout=300.0)
        self._require_output(dest, "decode")

    def encode_mp3(
        self, source_wav: Path, dest: Path, bitrate: str, cancel: Optional[CancelToken] = None
    ) -> None:
        exe = self.require()
        args = [
            str(exe), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-i", str(source_wav), "-vn", "-c:a", "libmp3lame", "-b:a", bitrate,
            "-f", "mp3", str(dest),
        ]
        self._run(args, cancel=cancel, timeout=1800.0)
        self._require_output(dest, "MP3 encode")

    def run_args(self, args: List[str], cancel: Optional[CancelToken] = None, timeout: float = 600.0) -> str:
        return self._run(args, cancel=cancel, timeout=timeout)

    def probe(self, path: Path, cancel: Optional[CancelToken] = None) -> MediaInfo:
        exe = self.require()
        path = Path(path)
        if not path.is_file():
            raise MediaError(f"File not found: {path}")
        _, stderr = self._run_probe_capture(
            [str(exe), "-hide_banner", "-nostdin", "-i", str(path)],
            path=path, operation="inspect", timeout=60.0, cancel=cancel, check_returncode=False,
        )
        return parse_probe_output(stderr.decode("utf-8", errors="replace"))

    def probe_structured(
        self, path: Path, *, count_frames: bool = False, count_packets: bool = False,
        cancel: Optional[CancelToken] = None,
    ) -> StructuredMediaInfo:
        """Inspect container and stream metadata with cancellable FFprobe execution.

        This is intentionally separate from probe(), which retains its legacy
        FFmpeg-banner parsing behavior for existing callers.
        """
        path = Path(path)
        if not path.is_file():
            raise MediaError(f"File not found: {path}")
        ffprobe = self._find_ffprobe()
        args = [str(ffprobe), "-v", "error"]
        if count_frames:
            args.append("-count_frames")
        if count_packets:
            args.append("-count_packets")
        args.extend(["-show_format", "-show_streams", "-of", "json", str(path)])
        stdout, _ = self._run_probe_capture(
            args, path=path, operation="inspect with FFprobe",
            timeout=(3600.0 if count_frames else 60.0), cancel=cancel,
        )
        return parse_ffprobe_json(stdout.decode("utf-8", errors="replace"))

    def probe_frame_timestamps(
        self, path: Path, expected_fps: int, cancel: Optional[CancelToken] = None
    ) -> FrameTimestampInfo:
        """Decode video frames and inspect CFR timestamps with cancellable FFprobe."""
        path = Path(path)
        if not path.is_file():
            raise MediaError(f"File not found: {path}")
        if expected_fps <= 0:
            raise ValueError("expected_fps must be positive")
        ffprobe = self._find_ffprobe()
        args = [
            str(ffprobe), "-v", "error", "-select_streams", "v:0",
            "-show_frames", "-show_entries", "frame=best_effort_timestamp_time",
            "-of", "json", str(path),
        ]
        stdout, _ = self._run_probe_capture(
            args, path=path, operation="inspect frame timestamps in",
            timeout=3600.0, cancel=cancel,
        )
        return parse_frame_timestamp_json(stdout.decode("utf-8", errors="replace"), expected_fps)

    def _run_probe_capture(
        self,
        args: List[str],
        *,
        path: Path,
        operation: str,
        timeout: float,
        cancel: Optional[CancelToken],
        check_returncode: bool = True,
    ) -> tuple[bytes, bytes]:
        """Run a media-inspection subprocess with bounded polling and cancellation."""
        if cancel is not None:
            cancel.raise_if_cancelled()
        try:
            proc = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            raise MediaError(f"Could not start FFprobe to {operation} '{path.name}': {exc}") from exc

        started = time.monotonic()
        try:
            while True:
                if cancel is not None and cancel.cancelled:
                    raise GenerationCancelled("Generation cancelled.")
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise MediaError(
                        f"Could not {operation} '{path.name}': inspection timed out after {int(timeout)} seconds."
                    )
                try:
                    stdout, stderr = proc.communicate(timeout=min(0.2, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            if cancel is not None:
                cancel.raise_if_cancelled()
            if check_returncode and proc.returncode != 0:
                detail = (stderr or b"").decode("utf-8", errors="replace").strip()
                detail = detail or f"FFprobe exited with code {proc.returncode}"
                raise MediaError(f"FFprobe could not {operation} '{path.name}': {detail}")
            return stdout or b"", stderr or b""
        except BaseException:
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
            try:
                proc.communicate()
            except (OSError, ValueError):
                pass
            raise

    def _find_ffprobe(self) -> Path:
        """Find FFprobe beside the selected FFmpeg, then on PATH."""
        ffmpeg = self.require()
        import os
        names = ("ffprobe.exe", "ffprobe") if os.name == "nt" else ("ffprobe",)
        candidates = [ffmpeg.with_name(name) for name in names]
        found = shutil.which("ffprobe")
        if found:
            candidates.append(Path(found))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise MediaError(
            "FFprobe is required for structured media inspection but was not found. "
            "Install the FFmpeg package that includes ffprobe.exe, or add ffprobe to PATH."
        )

    def run_with_progress(
        self,
        args: List[str],
        total_seconds: float,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[CancelToken] = None,
        timeout: float = 6 * 3600.0,
    ) -> None:
        """Run FFmpeg and report progress, cleaning up its reader and pipe on every exit."""
        command = [args[0], "-progress", "pipe:1", "-nostats", *args[1:]]
        try:
            proc = subprocess.Popen(
                command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            raise FFmpegError(f"Could not start FFmpeg: {exc}") from exc

        lines: "queue.Queue[Optional[str]]" = queue.Queue()

        def reader() -> None:
            try:
                assert proc.stdout is not None
                with proc.stdout:
                    for raw in iter(proc.stdout.readline, b""):
                        lines.put(raw.decode("utf-8", errors="replace").strip())
            except (OSError, ValueError):
                logger.debug("FFmpeg progress pipe closed while reader was active")
            finally:
                lines.put(None)

        reader_thread = threading.Thread(
            target=reader, name="FFmpegProgressReader", daemon=True
        )
        reader_thread.start()
        started = time.monotonic()
        tail: List[str] = []
        try:
            finished = False
            while not finished:
                try:
                    line = lines.get(timeout=0.2)
                except queue.Empty:
                    line = ""
                if line is None:
                    finished = True
                elif line:
                    key, _, value = line.partition("=")
                    if key in ("out_time_us", "out_time_ms") and value.isdigit() and total_seconds > 0:
                        if on_progress:
                            on_progress(min(1.0, int(value) / 1e6 / total_seconds))
                    elif key not in ("progress", "frame", "fps", "stream_0_0_q", "bitrate", "total_size",
                                     "out_time", "dup_frames", "drop_frames", "speed"):
                        tail.append(line)
                        tail = tail[-6:]
                if cancel is not None and cancel.cancelled:
                    raise GenerationCancelled("Generation cancelled.")
                if time.monotonic() - started > timeout:
                    raise FFmpegError("FFmpeg timed out.")

            proc.wait()
            if proc.returncode != 0:
                detail = tail[-1] if tail else "no error output"
                logger.error("FFmpeg failed (exit %s): %s", proc.returncode, " | ".join(tail))
                raise FFmpegError(f"FFmpeg failed (exit code {proc.returncode}): {detail}")
        finally:
            # A progress callback can fail too; never leave the child process or
            # reader thread running when any path exits this method.
            try:
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except OSError:
                        pass
                proc.wait()
            finally:
                reader_thread.join()
                if proc.stdout is not None and not proc.stdout.closed:
                    proc.stdout.close()

        if on_progress:
            on_progress(1.0)

    @staticmethod
    def _require_output(dest: Path, what: str) -> None:
        if not dest.is_file() or dest.stat().st_size == 0:
            raise FFmpegError(f"FFmpeg {what} produced no output file.")

    def _run(self, args: List[str], cancel: Optional[CancelToken] = None, timeout: float = 300.0) -> str:
        try:
            proc = subprocess.Popen(
                args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
            )
        except OSError as exc:
            raise FFmpegError(f"Could not start FFmpeg: {exc}") from exc

        started = time.monotonic()
        while True:
            try:
                out, err = proc.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.cancelled:
                    self._kill(proc)
                    raise GenerationCancelled("Generation cancelled.")
                if time.monotonic() - started > timeout:
                    self._kill(proc)
                    raise FFmpegError(f"FFmpeg timed out after {int(timeout)} seconds.")

        if proc.returncode != 0:
            tail = (err or b"").decode("utf-8", errors="replace").strip().splitlines()
            detail = tail[-1] if tail else "no error output"
            logger.error("FFmpeg failed (exit %s): %s", proc.returncode, detail)
            raise FFmpegError(f"FFmpeg failed (exit code {proc.returncode}): {detail}")
        return (out or b"").decode("utf-8", errors="replace")

    @staticmethod
    def _kill(proc: "subprocess.Popen[bytes]") -> None:
        try:
            proc.kill()
            proc.communicate()
        except Exception:
            pass
