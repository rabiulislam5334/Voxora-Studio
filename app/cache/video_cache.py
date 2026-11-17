from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, List, Optional

from app.core.constants import (
    VIDEO_CACHE_MAX_BYTES,
    VIDEO_IMAGE_CACHE_MAX_BYTES,
    VIDEO_PIPELINE_VERSION,
)
from app.core.logger import get_logger

logger = get_logger("cache.video")

# A short grace period keeps files used by a just-finished or concurrently
# running render out of an eviction pass. A later prune can reclaim them.
_CACHE_PRUNE_GRACE_SECONDS = 120


def media_identity(path: Path) -> List[Any]:
    """What identifies a media file's CONTENT cheaply: resolved path, size and
    modification time. Editing or replacing the file changes the identity, so
    a cached segment made from the old file is never reused."""
    path = Path(path)
    try:
        stat = path.stat()
        return [str(path.resolve()), stat.st_size, stat.st_mtime_ns]
    except OSError:
        return [str(path), -1, -1]


class VideoCache:
    """Cache of rendered scene segments (silent MP4s), thumbnails and
    waveform images, all under one machine-local folder. Keys hash every
    input that affects the picture (media identity, length, size, fps, motion,
    fit, pipeline version) and nothing else -- changing e.g. the music volume
    or narration voice never invalidates cached video."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.segments_dir = self.root / "segments"
        self.images_dir = self.root / "images"
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _hash(payload: Any) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def segment_key(self, spec) -> str:
        identity = media_identity(Path(spec.media)) if spec.media else None
        return self._hash([
            VIDEO_PIPELINE_VERSION, spec.kind, identity, spec.frames, spec.length_ticks,
            spec.width, spec.height, spec.fps, spec.motion, spec.fit,
        ])

    def segment_path(self, key: str) -> Path:
        return self.segments_dir / f"{key}.mp4"

    def has_segment(self, key: str) -> bool:
        path = self.segment_path(key)
        return path.is_file() and path.stat().st_size > 0

    def touch_segment(self, key: str) -> None:
        """Refresh a segment's LRU timestamp after a successful cache hit."""
        try:
            os.utime(self.segment_path(key), None)
        except OSError:
            pass

    def part_path(self, key: str) -> Path:
        return self.segments_dir / f"{key}.{uuid.uuid4().hex[:8]}.part"

    def commit_segment(self, part: Path, key: str) -> Path:
        if not part.is_file() or part.stat().st_size == 0:
            raise OSError("rendered segment is missing or empty")
        final = self.segment_path(key)
        os.replace(part, final)
        return final

    def image_path(self, kind: str, source: Path, *extra: Any) -> Path:
        key = self._hash([VIDEO_PIPELINE_VERSION, kind, media_identity(source), list(extra)])
        return self.images_dir / f"{kind}_{key[:32]}.png"

    def touch_image(self, path: Path) -> None:
        """Refresh a preview image's LRU timestamp after a successful cache hit."""
        try:
            candidate = Path(path)
            if candidate.parent.resolve() != self.images_dir.resolve():
                return
            os.utime(candidate, None)
        except OSError:
            pass

    def _prune_directory(
        self,
        directory: Path,
        pattern: str,
        max_bytes: int,
        *,
        now: Optional[float] = None,
        grace_seconds: float = _CACHE_PRUNE_GRACE_SECONDS,
    ) -> None:
        """Evict least-recently-used files, leaving recent/touched files alone.

        The mtime snapshot is rechecked immediately before unlinking so a file
        touched after the scan began is not removed based on stale LRU data.
        Temporary .part files and symlinks are never candidates.
        """
        budget = max(0, int(max_bytes))
        current_time = time.time() if now is None else float(now)
        cutoff_ns = int((current_time - max(0.0, grace_seconds)) * 1_000_000_000)
        candidates = []
        try:
            for path in directory.glob(pattern):
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    stat = path.stat()
                except OSError:
                    continue
                candidates.append((stat.st_mtime_ns, path.name, path, stat.st_size))
        except OSError as exc:
            logger.warning("Could not scan cache directory %s: %s", directory, exc)
            return

        total = sum(item[3] for item in candidates)
        candidates.sort(key=lambda item: (item[0], item[1]))
        for recorded_mtime_ns, _name, path, _recorded_size in candidates:
            if total <= budget:
                break
            if recorded_mtime_ns >= cutoff_ns:
                continue
            try:
                current = path.stat()
                if path.is_symlink() or not path.is_file():
                    continue
                # A concurrent cache hit/commit refreshed this entry after the
                # initial scan. Re-sort on the next prune rather than deleting it.
                if current.st_mtime_ns != recorded_mtime_ns:
                    continue
                path.unlink()
                total -= current.st_size
            except FileNotFoundError:
                continue
            except OSError as exc:
                logger.warning("Could not prune cache entry %s: %s", path.name, exc)

    def prune_images(
        self,
        max_bytes: int = VIDEO_IMAGE_CACHE_MAX_BYTES,
        *,
        now: Optional[float] = None,
        grace_seconds: float = _CACHE_PRUNE_GRACE_SECONDS,
    ) -> None:
        """Bound thumbnail/waveform storage independently from rendered MP4s."""
        self._prune_directory(
            self.images_dir, "*.png", max_bytes, now=now, grace_seconds=grace_seconds
        )

    def prune(
        self,
        max_bytes: int = VIDEO_CACHE_MAX_BYTES,
        *,
        image_max_bytes: int = VIDEO_IMAGE_CACHE_MAX_BYTES,
        now: Optional[float] = None,
        grace_seconds: float = _CACHE_PRUNE_GRACE_SECONDS,
    ) -> None:
        """Apply independent LRU byte budgets to segments and preview images."""
        self._prune_directory(
            self.segments_dir, "*.mp4", max_bytes, now=now, grace_seconds=grace_seconds
        )
        self.prune_images(
            image_max_bytes, now=now, grace_seconds=grace_seconds
        )
