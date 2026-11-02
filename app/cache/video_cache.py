from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any, List

from app.core.constants import VIDEO_CACHE_MAX_BYTES, VIDEO_PIPELINE_VERSION
from app.core.logger import get_logger

logger = get_logger("cache.video")


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
            VIDEO_PIPELINE_VERSION, spec.kind, identity, round(spec.length_s, 3),
            spec.width, spec.height, spec.fps, spec.motion, spec.fit,
        ])

    def segment_path(self, key: str) -> Path:
        return self.segments_dir / f"{key}.mp4"

    def has_segment(self, key: str) -> bool:
        path = self.segment_path(key)
        return path.is_file() and path.stat().st_size > 0

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

    def prune(self, max_bytes: int = VIDEO_CACHE_MAX_BYTES) -> None:
        """Delete the least recently written segments once the cache is too big."""
        try:
            files = [p for p in self.segments_dir.glob("*.mp4")]
            files.sort(key=lambda p: p.stat().st_mtime)
            total = sum(p.stat().st_size for p in files)
        except OSError:
            return
        for old in files:
            if total <= max_bytes:
                break
            try:
                size = old.stat().st_size
                old.unlink()
                total -= size
            except OSError as exc:
                logger.warning("Could not prune %s: %s", old.name, exc)

    def remove_stale_parts(self) -> None:
        for part in list(self.segments_dir.glob("*.part")):
            try:
                part.unlink()
            except OSError:
                pass