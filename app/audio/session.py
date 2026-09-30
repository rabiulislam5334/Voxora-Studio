from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from app.core.exceptions import AudioProcessingError
from app.core.logger import get_logger

logger = get_logger("audio.session")


class GeneratedAudioSession:
    """Tracks the single "currently generated" temporary audio file and
    handles exporting it (Save As) and cleaning up the previous temp file
    once it's safely replaced.

    This is deliberately UI-free (no Tkinter) so it can be unit tested
    directly. It also holds the fix for the Phase 2 output-directory bug:
    generation ALWAYS writes to one deterministic app-owned temp
    directory -- there is no longer a second, independently-editable
    "output folder" field that generation could silently disagree with.
    Permanent export only ever happens through save_as(), which always
    asks the OS for an explicit destination.
    """

    def __init__(self, temp_dir: Path) -> None:
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.current_path: Optional[Path] = None
        self.is_saved: bool = True  # no unsaved audio until something is generated
        self.last_saved_path: Optional[Path] = None

    def adopt_new_generation(self, new_path: Path) -> None:
        """Register a freshly generated file as the current one. The
        caller (VoicePanel) is responsible for making sure playback of
        the OLD file has been stopped/reloaded-away-from before calling
        this, so the old file is never deleted while still open/playing
        (Windows will refuse the delete anyway if it's still locked --
        that failure is caught and logged, not raised, since an orphaned
        temp file is harmless clutter, not data loss)."""
        previous = self.current_path
        self.current_path = Path(new_path)
        self.is_saved = False
        self.last_saved_path = None

        if previous is not None and previous != self.current_path and previous.exists():
            try:
                previous.unlink()
            except OSError as exc:
                logger.warning("Could not remove previous temp audio %s: %s", previous, exc)

    def save_as(self, destination: Path) -> Path:
        """Copy the current temp audio to a permanent destination the user
        chose. Returns the destination path. Raises AudioProcessingError
        on any failure -- callers must not report success unless this
        returns normally."""
        if self.current_path is None or not self.current_path.exists():
            raise AudioProcessingError("There is no generated audio to save.")

        destination = Path(destination)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.current_path, destination)
        except OSError as exc:
            logger.exception("Save As failed: %s -> %s", self.current_path, destination)
            raise AudioProcessingError(f"Could not save the file: {exc}") from exc

        if not destination.exists() or destination.stat().st_size == 0:
            raise AudioProcessingError("The exported file could not be verified after saving.")

        self.is_saved = True
        self.last_saved_path = destination
        logger.info("Saved generated audio to %s", destination)
        return destination

    def cleanup(self) -> None:
        """Remove the current temp file, if any. Safe to call on shutdown
        or when discarding audio; never touches an already-exported copy
        since save_as() only ever copies, never moves."""
        if self.current_path is not None and self.current_path.exists():
            try:
                self.current_path.unlink()
            except OSError as exc:
                logger.warning("Could not remove temp audio %s during cleanup: %s", self.current_path, exc)
        self.current_path = None