from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Optional

from app.core.exceptions import AudioProcessingError

_SAMPLE_WIDTH = 2  # 16-bit PCM
_CHANNELS = 1
_BLOCK_FRAMES = 65536


def wav_duration_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as reader:
            return reader.getnframes() / float(reader.getframerate())
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioProcessingError(f"Could not read WAV file '{Path(path).name}': {exc}") from exc


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
    def duration_seconds(self) -> float:
        return self.frames / float(self.sample_rate)

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
        if milliseconds <= 0:
            return
        remaining = round(milliseconds * self.sample_rate / 1000.0)
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