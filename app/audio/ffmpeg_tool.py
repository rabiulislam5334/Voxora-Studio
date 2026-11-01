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

from app.audio.probe import MediaInfo, parse_probe_output
from app.core.exceptions import FFmpegError, GenerationCancelled, MediaError
from app.core.logger import get_logger
from app.core.settings_store import SettingsStore
from app.workers.cancel import CancelToken

logger = get_logger("audio.ffmpeg")

SETTINGS_KEY = "ffmpeg_path"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows only; 0 elsewhere
_INSTALL_HINT = (
    "Install FFmpeg (for example: winget install --id Gyan.FFmpeg -e), restart the app, "
    "or choose ffmpeg.exe with 'Set Path...'."
)


@dataclass(frozen=True)
class FFmpegStatus:
    available: bool
    path: Optional[Path]
    version: Optional[str]
    source: str  # "settings" | "path" | "imageio" | "none"
    message: str


class FFmpegTool:
    """Locates, verifies and runs FFmpeg.

    Detection order: path saved in settings -> `ffmpeg` on PATH -> the
    optional `imageio-ffmpeg` binary (only if that package happens to be
    installed). A candidate is trusted only after `ffmpeg -version` succeeds
    AND the build lists the libmp3lame encoder (needed for MP3 export).

    Every command is an argument LIST -- never a shell string -- so file names
    (spaces, Bengali characters, quotes) cannot be misinterpreted.
    """

    def __init__(self, settings: SettingsStore) -> None:
        self._settings = settings
        self._status: Optional[FFmpegStatus] = None

    # ------------------------------------------------------------------
    # Configuration / detection
    # ------------------------------------------------------------------

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
        """Blocking (runs `ffmpeg -version`); call from a worker thread."""
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
        """Return a verified ffmpeg path or raise FFmpegError with a clear,
        actionable message. Re-detects if FFmpeg disappeared since last check."""
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
        try:  # optional fallback; never a required dependency
            import imageio_ffmpeg  # type: ignore[import-not-found]

            yield "imageio", Path(imageio_ffmpeg.get_exe())
        except Exception:  # noqa: BLE001 - ImportError or runtime lookup failure
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

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def decode_to_wav(
        self, source: Path, dest: Path, sample_rate: int, cancel: Optional[CancelToken] = None
    ) -> None:
        """Decode any audio file to mono 16-bit PCM WAV at `sample_rate`."""
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
        """Public wrapper: run a prepared ffmpeg argument list (no shell)."""
        return self._run(args, cancel=cancel, timeout=timeout)

    # ------------------------------------------------------------------
    # Phases 6-8: probing and long-running commands with progress
    # ------------------------------------------------------------------

    def probe(self, path: Path) -> MediaInfo:
        """Describe a media file (duration, streams, size) using only ffmpeg,
        so it works even when ffprobe is not installed. Raises MediaError."""
        exe = self.require()
        path = Path(path)
        if not path.is_file():
            raise MediaError(f"File not found: {path}")
        try:
            proc = subprocess.run(
                [str(exe), "-hide_banner", "-nostdin", "-i", str(path)],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=_NO_WINDOW, timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MediaError(f"Could not inspect '{path.name}': {exc}") from exc
        return parse_probe_output(proc.stderr.decode("utf-8", errors="replace"))

    def run_with_progress(
        self,
        args: List[str],
        total_seconds: float,
        on_progress: Optional[Callable[[float], None]] = None,
        cancel: Optional[CancelToken] = None,
        timeout: float = 6 * 3600.0,
    ) -> None:
        """Run `args` (args[0] must be the ffmpeg path) and report progress as
        a 0..1 fraction of `total_seconds` of output. Cancel terminates the
        process. Never uses a shell."""
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
            assert proc.stdout is not None
            for raw in iter(proc.stdout.readline, b""):
                lines.put(raw.decode("utf-8", errors="replace").strip())
            lines.put(None)

        threading.Thread(target=reader, daemon=True).start()
        started = time.monotonic()
        tail: List[str] = []
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
                self._kill(proc)
                raise GenerationCancelled("Generation cancelled.")
            if time.monotonic() - started > timeout:
                self._kill(proc)
                raise FFmpegError("FFmpeg timed out.")
        proc.wait()
        if proc.returncode != 0:
            detail = tail[-1] if tail else "no error output"
            logger.error("FFmpeg failed (exit %s): %s", proc.returncode, " | ".join(tail))
            raise FFmpegError(f"FFmpeg failed (exit code {proc.returncode}): {detail}")
        if on_progress:
            on_progress(1.0)

    @staticmethod
    def _require_output(dest: Path, what: str) -> None:
        if not dest.is_file() or dest.stat().st_size == 0:
            raise FFmpegError(f"FFmpeg {what} produced no output file.")

    def _run(self, args: List[str], cancel: Optional[CancelToken] = None, timeout: float = 300.0) -> str:
        """Run an argument list (never through a shell). Polls so a cancel
        request terminates the child process promptly."""
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=_NO_WINDOW,
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
        except Exception:  # noqa: BLE001 - best effort during cancellation
            pass