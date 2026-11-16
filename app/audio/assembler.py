from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Optional

from app.core.exceptions import AudioProcessingError
from app.core.timebase import samples_to_ticks, ticks_to_samples, ticks_to_seconds

_SAMPLE_WIDTH = 2  # 16-bit PCM
_CHANNELS = 1
_BLOCK_FRAMES = 65536


def wav_duration_ticks(path: Path) -> int:
    """Return the exact duration represented by the WAV sample count."""
    try:
        with wave.open(str(path), "rb") as reader:
            return samples_to_ticks(reader.getnframes(), reader.getframerate(), rounding="exact")
    except (wave.Error, EOFError, OSError, ValueError, TypeError) as exc:
        raise AudioProcessingError(f"Could not read WAV file '{Path(path).name}': {exc}") from exc


def wav_duration_seconds(path: Path) -> float:
    """Compatibility seconds view; WAV sample count remains authoritative."""
    return float(ticks_to_seconds(wav_duration_ticks(path)))


class WavBuilder:
    """Streams mono 16-bit PCM WAV audio and digital silence into one file.

    Uses only the standard library `wave` module and fixed-size blocks, so
    memory stays flat no matter how long the narration is, and silence is
    EXACT (all-zero samples). Output is written to `<dest>.part` and renamed
    on success; on any error the partial file is removed.
    """

    def __init__(self, dest: Path, sample_rate: int) -> None:
        self.dest = Path(dest)
        self.sample_rate = sample_rate
        self._part = self.dest.with_name(self.dest.name + ".part")
        self._writer: Optional[wave.Wave_write] = None
        self.frames = 0

    @property
    def duration_ticks(self) -> int:
        """Exact timeline duration derived from the number of written samples."""
        return samples_to_ticks(self.frames, self.sample_rate, rounding="exact")

    @property
    def duration_seconds(self) -> float:
        """Compatibility view derived from the authoritative sample count."""
        return float(ticks_to_seconds(self.duration_ticks))

    def __enter__(self) -> "WavBuilder":
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        self._writer = wave.open(str(self._part), "wb")
        self._writer.setnchannels(_CHANNELS)
        self._writer.setsampwidth(_SAMPLE_WIDTH)
        self._writer.setframerate(self.sample_rate)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        writer, self._writer = self._writer, None
        try:
            if writer is not None:
                writer.close()
        finally:
            if exc_type is None:
                try:
                    os.replace(self._part, self.dest)
                except OSError as err:
                    self._part.unlink(missing_ok=True)
                    raise AudioProcessingError(f"Could not finalize '{self.dest.name}': {err}") from err
            else:
                self._part.unlink(missing_ok=True)
        return False

    def add_silence(self, milliseconds: int) -> None:
        """Legacy millisecond API; retains its historical sample rounding."""
        if milliseconds <= 0:
            return
        self.add_silence_samples(round(milliseconds * self.sample_rate / 1000.0))

    def add_silence_ticks(self, ticks: int) -> None:
        """Append silence for an exact canonical duration.

        The requested tick duration must map to a whole sample at this WAV's
        sample rate; this prevents silently drifting the audio timeline.
        """
        self.add_silence_samples(ticks_to_samples(ticks, self.sample_rate, rounding="exact"))

    def add_silence_samples(self, samples: int) -> None:
        if isinstance(samples, bool) or not isinstance(samples, int):
            raise TypeError("samples must be an integer")
        if samples < 0:
            raise ValueError("samples must be non-negative")
        remaining = samples
        block = b"\x00" * (_BLOCK_FRAMES * _SAMPLE_WIDTH * _CHANNELS)
        while remaining > 0:
            n = min(remaining, _BLOCK_FRAMES)
            self._write(block[: n * _SAMPLE_WIDTH * _CHANNELS])
            self.frames += n
            remaining -= n

    def add_wav(self, source: Path) -> None:
        try:
            with wave.open(str(source), "rb") as reader:
                if (
                    reader.getnchannels() != _CHANNELS
                    or reader.getsampwidth() != _SAMPLE_WIDTH
                    or reader.getframerate() != self.sample_rate
                ):
                    raise AudioProcessingError(
                        f"'{Path(source).name}' is not {self.sample_rate} Hz mono 16-bit PCM."
                    )
                while True:
                    data = reader.readframes(_BLOCK_FRAMES)
                    if not data:
                        break
                    self._write(data)
                    self.frames += len(data) // (_SAMPLE_WIDTH * _CHANNELS)
        except (wave.Error, EOFError, OSError) as exc:
            raise AudioProcessingError(f"Could not read WAV file '{Path(source).name}': {exc}") from exc

    def _write(self, data: bytes) -> None:
        if self._writer is None:
            raise AudioProcessingError("WavBuilder is not open.")
        try:
            self._writer.writeframes(data)
        except OSError as exc:
            raise AudioProcessingError(f"Could not write audio (disk full?): {exc}") from exc