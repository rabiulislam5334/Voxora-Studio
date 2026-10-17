from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from app.core.exceptions import FFmpegError, GenerationCancelled
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