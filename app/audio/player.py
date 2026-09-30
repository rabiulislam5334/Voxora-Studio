from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from app.core.exceptions import AudioProcessingError
from app.core.logger import get_logger

logger = get_logger("audio.player")

_mixer_lock = threading.Lock()
_mixer_initialized = False


def _ensure_mixer_ready() -> None:
    """Initialize pygame's audio subsystem exactly once, process-wide.

    Deferred to first use so the rest of the app (generation, filenames,
    etc.) works even on a machine with no audio device -- only playback
    itself becomes unavailable, and that failure is reported cleanly
    rather than crashing at import time.
    """
    global _mixer_initialized
    with _mixer_lock:
        if _mixer_initialized:
            return
        try:
            import pygame

            pygame.mixer.init()
        except Exception as exc:
            logger.exception("Failed to initialize the audio playback backend")
            raise AudioProcessingError(
                f"Could not initialize the audio playback system: {exc}"
            ) from exc
        _mixer_initialized = True


class PlaybackState(Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass(frozen=True)
class PlaybackStatus:
    state: PlaybackState
    position_seconds: float
    duration_seconds: float


class AudioPlayer:
    """Full transport control (play/pause/resume/stop/seek/volume) for a
    single track at a time, backed by pygame.mixer.music -- the one
    streaming "music" channel pygame provides, appropriate for narration
    that may run several minutes long in later phases.

    IMPORTANT: pygame.mixer.music.get_busy() returns False both when the
    track is paused AND when it has finished -- it cannot distinguish the
    two on its own. This class keeps its own authoritative state machine
    and only consults get_busy() to detect natural end-of-track while our
    own state says PLAYING (verified against real pygame 2.6 behavior
    before shipping this).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = PlaybackState.STOPPED
        self._current_path: Optional[Path] = None
        self._duration = 0.0
        self._position_at_last_action = 0.0
        self._action_started_at: Optional[float] = None  # time.monotonic()
        self._volume = 1.0

    # -- loading ---------------------------------------------------------

    def load(self, path: Path) -> float:
        """Load a file for playback (stopping whatever was playing first)
        and return its duration in seconds (0.0 if unreadable)."""
        _ensure_mixer_ready()
        import pygame

        with self._lock:
            self.stop()
            try:
                pygame.mixer.music.load(str(path))
            except Exception as exc:
                logger.exception("Failed to load audio file: %s", path)
                raise AudioProcessingError(f"Could not load audio: {exc}") from exc

            self._current_path = path
            self._duration = self._probe_duration(path)
            self._position_at_last_action = 0.0
            self._action_started_at = None
            self._state = PlaybackState.STOPPED
            return self._duration

    @staticmethod
    def _probe_duration(path: Path) -> float:
        """Uses mutagen's generic auto-detecting File() (not the MP3-only
        API) so duration probing also works for other formats pygame can
        play, not just MP3 -- with no cost to the common MP3 case."""
        try:
            import mutagen

            audio = mutagen.File(str(path))
            if audio is None or audio.info is None:
                return 0.0
            return float(audio.info.length)
        except Exception:
            logger.warning("Could not read duration metadata for %s", path)
            return 0.0

    # -- transport ---------------------------------------------------------

    def play(self, start_seconds: float = 0.0) -> None:
        _ensure_mixer_ready()
        import pygame

        with self._lock:
            if self._current_path is None:
                raise AudioProcessingError("No audio is loaded.")
            try:
                pygame.mixer.music.play(start=max(0.0, start_seconds))
                pygame.mixer.music.set_volume(self._volume)
            except Exception as exc:
                logger.exception("Playback failed to start for %s", self._current_path)
                raise AudioProcessingError(f"Could not start playback: {exc}") from exc
            self._position_at_last_action = start_seconds
            self._action_started_at = time.monotonic()
            self._state = PlaybackState.PLAYING

    def pause(self) -> None:
        import pygame

        with self._lock:
            if self._state != PlaybackState.PLAYING:
                return
            pygame.mixer.music.pause()
            self._position_at_last_action = self._locked_position()
            self._action_started_at = None
            self._state = PlaybackState.PAUSED

    def resume(self) -> None:
        import pygame

        with self._lock:
            if self._state != PlaybackState.PAUSED:
                return
            pygame.mixer.music.unpause()
            self._action_started_at = time.monotonic()
            self._state = PlaybackState.PLAYING

    def stop(self) -> None:
        with self._lock:
            if _mixer_initialized:
                import pygame

                pygame.mixer.music.stop()
            self._position_at_last_action = 0.0
            self._action_started_at = None
            self._state = PlaybackState.STOPPED

    def seek(self, seconds: float) -> None:
        with self._lock:
            if self._current_path is None:
                return
            clamped = max(0.0, min(seconds, self._duration) if self._duration else max(0.0, seconds))
            was_paused = self._state == PlaybackState.PAUSED
            self.play(start_seconds=clamped)
            if was_paused:
                self.pause()

    def set_volume(self, volume: float) -> None:
        with self._lock:
            self._volume = max(0.0, min(1.0, volume))
            if _mixer_initialized:
                import pygame

                pygame.mixer.music.set_volume(self._volume)

    # -- status ---------------------------------------------------------

    def _locked_position(self) -> float:
        """Caller must hold self._lock."""
        if self._state == PlaybackState.PLAYING and self._action_started_at is not None:
            elapsed = time.monotonic() - self._action_started_at
            position = self._position_at_last_action + elapsed
            if self._duration:
                return min(position, self._duration)
            return position
        return self._position_at_last_action

    def get_status(self) -> PlaybackStatus:
        with self._lock:
            if self._state == PlaybackState.PLAYING and _mixer_initialized:
                import pygame

                if not pygame.mixer.music.get_busy():
                    # get_busy() is False both when paused and when finished;
                    # since our own state says PLAYING (not PAUSED), this
                    # can only mean the track ended naturally.
                    self._state = PlaybackState.STOPPED
                    self._position_at_last_action = 0.0
                    self._action_started_at = None
            return PlaybackStatus(
                state=self._state,
                position_seconds=self._locked_position(),
                duration_seconds=self._duration,
            )

    def shutdown(self) -> None:
        with self._lock:
            if _mixer_initialized:
                import pygame

                try:
                    pygame.mixer.music.stop()
                except Exception:
                    logger.debug("Error stopping music on shutdown", exc_info=True)
            self._state = PlaybackState.STOPPED


class VoicePreviewPlayer:
    """Fire-and-forget playback for short voice-library preview clips.

    Uses pygame.mixer.Sound on its own channel -- independent of whatever
    is loaded in the main AudioPlayer's music channel, so previewing a
    voice never disturbs (or is disturbed by) the generated-audio player.
    Runs on a daemon thread since Sound loading briefly blocks on file I/O.
    """

    def play(
        self,
        path: Path,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        threading.Thread(
            target=self._play_blocking, args=(path, on_error), daemon=True
        ).start()

    def _play_blocking(
        self, path: Path, on_error: Optional[Callable[[Exception], None]]
    ) -> None:
        try:
            _ensure_mixer_ready()
            import pygame

            sound = pygame.mixer.Sound(str(path))
            sound.play()
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            logger.exception("Preview playback failed for %s", path)
            if on_error:
                on_error(AudioProcessingError(f"Could not play preview: {exc}"))