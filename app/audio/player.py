from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from app.core.exceptions import AudioProcessingError
from app.core.logger import get_logger

logger = get_logger("audio.player")


class AudioPlayer:
    """Minimal non-blocking MP3/WAV playback for voice previews.

    Uses the `playsound` package (a thin wrapper over the OS's native media
    APIs) rather than a full audio engine like pygame -- previews are short
    clips, and this keeps Phase 2 dependencies light (important on an 8 GB
    machine). Playback runs on its own daemon thread so a blocking call
    inside `playsound` never freezes the Tk UI.
    """

    def play(
        self,
        path: Path,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        thread = threading.Thread(
            target=self._play_blocking, args=(path, on_error), daemon=True
        )
        thread.start()

    def _play_blocking(
        self, path: Path, on_error: Optional[Callable[[Exception], None]]
    ) -> None:
        try:
            from playsound import playsound  # imported lazily; optional at runtime

            playsound(str(path))
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
            logger.exception("Playback failed for %s", path)
            if on_error:
                on_error(AudioProcessingError(f"Could not play audio: {exc}"))