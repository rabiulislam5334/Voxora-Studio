from __future__ import annotations

import hashlib
import json
import os
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Iterable

from app.core.constants import NARRATION_PIPELINE_VERSION, NARRATION_SCENE_PIPELINE_VERSION
from app.core.logger import get_logger

logger = get_logger("cache.narration")

_WAV_HEADER_BYTES = 44
_STALE_PART_SECONDS = 600


class NarrationCache:
    """Two machine-local caches (never referenced from .voxora files):

    * chunks/  -- one MP3 per synthesized chunk, keyed by a deterministic
                  SHA-256 of everything that affects the audio.
    * scenes/  -- one assembled WAV per scene, keyed by its full plan.

    Files are written under a unique `.part` name and renamed into place, so
    a crash or cancel can never leave a half-written file that looks valid.
    """

    def __init__(self, chunks_dir: Path, scenes_dir: Path) -> None:
        self.chunks_dir = Path(chunks_dir)
        self.scenes_dir = Path(scenes_dir)
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.scenes_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- chunk cache ----------------

    @staticmethod
    def chunk_key(
        provider_id: str, voice_id: str, text: str, rate: float, pitch_hz: int, volume_percent: int
    ) -> str:
        payload = [
            NARRATION_PIPELINE_VERSION, provider_id, voice_id,
            unicodedata.normalize("NFC", text), round(float(rate), 3), int(pitch_hz), int(volume_percent),
        ]
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def chunk_path(self, key: str) -> Path:
        return self.chunks_dir / key[:2] / f"{key}.mp3"

    def part_path(self, key: str) -> Path:
        folder = self.chunks_dir / key[:2]
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{key}.{uuid.uuid4().hex[:8]}.part"

    def has_chunk(self, key: str) -> bool:
        path = self.chunk_path(key)
        return path.is_file() and path.stat().st_size > 0

    def commit_chunk(self, part: Path, key: str) -> Path:
        if not part.is_file() or part.stat().st_size == 0:
            raise OSError("synthesized chunk is missing or empty")
        final = self.chunk_path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(part, final)
        return final

    # ---------------- scene cache ----------------

    @staticmethod
    def scene_key(plan_signature: Iterable) -> str:
        payload = [NARRATION_SCENE_PIPELINE_VERSION, list(plan_signature)]
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def scene_wav_path(self, key: str) -> Path:
        return self.scenes_dir / f"{key}.wav"

    def has_scene(self, key: str) -> bool:
        path = self.scene_wav_path(key)
        return path.is_file() and path.stat().st_size > _WAV_HEADER_BYTES

    def prune_scene_wavs(self, max_files: int = 24) -> None:
        """Scene WAVs are large; keep only the most recently used few."""
        try:
            files = sorted(self.scenes_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return
        for old in files[max_files:]:
            try:
                old.unlink()
            except OSError as exc:
                logger.warning("Could not prune cached scene %s: %s", old.name, exc)

    def touch_scene(self, key: str) -> None:
        try:
            os.utime(self.scene_wav_path(key), None)
        except OSError:
            pass

    def remove_stale_parts(self) -> None:
        """Delete leftover .part files from an interrupted earlier run."""
        cutoff = time.time() - _STALE_PART_SECONDS
        for folder in (self.chunks_dir, self.scenes_dir):
            try:
                parts = list(folder.rglob("*.part"))
            except OSError:
                continue
            for part in parts:
                try:
                    if part.stat().st_mtime < cutoff:
                        part.unlink()
                except OSError:
                    pass