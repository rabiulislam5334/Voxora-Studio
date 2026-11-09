"""Rolling backups of project files, kept per project.

Before an existing project file is overwritten, the bytes that are about to
be replaced are written here (from the verified in-memory copy, not by
copying the file again). The newest ``keep`` backups are retained.

Layout::

    <root>/<project_id>/<YYYYmmdd-HHMMSS-mmm>-<NN>_<stem>.voxora

The fixed-width timestamp and counter make lexicographic order equal
chronological order. Backups are written atomically, so a partial backup
never appears in a listing. Pruning failures are logged and never abort a
save; a failure to *create* a backup raises ``BackupError`` and the caller
decides (the repository aborts the save by default).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List

from app.core.logger import get_logger
from app.persistence.atomic import atomic_write_bytes

logger = get_logger("persistence.backups")

DEFAULT_KEEP = 5
_NAME_RE = re.compile(r"^(\d{8}-\d{6}-\d{3})-(\d{2})_(.+)\.voxora$")
_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class BackupError(Exception):
    """A backup could not be created, listed or restored."""


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    project_id: str
    timestamp: str  # "YYYYmmdd-HHMMSS-mmm"
    stem: str


def _safe(text: str, fallback: str, limit: int = 80) -> str:
    # Only characters Windows rejects are replaced, so Bengali and other
    # Unicode names stay readable.
    cleaned = _UNSAFE_RE.sub("_", text).strip(" .")
    return (cleaned or fallback)[:limit]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BackupStore:
    def __init__(
        self,
        root: Path,
        keep: int = DEFAULT_KEEP,
        *,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if keep < 1:
            raise ValueError("keep must be at least 1")
        self._root = Path(root)
        self._keep = keep
        self._clock = clock
        self._sleep = sleep

    @property
    def keep(self) -> int:
        return self._keep

    def _folder(self, project_id: str) -> Path:
        return self._root / _safe(project_id, "unknown")

    def create_from_bytes(self, project_id: str, stem: str, data: bytes) -> Path:
        """Write ``data`` as a new backup of ``project_id``; prune old ones."""
        folder = self._folder(project_id)
        now = self._clock().astimezone(timezone.utc)
        stamp = now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"
        safe_stem = _safe(stem, "project")
        dest = None
        try:
            for counter in range(100):
                candidate = folder / f"{stamp}-{counter:02d}_{safe_stem}.voxora"
                if not candidate.exists():
                    dest = candidate
                    break
            if dest is None:
                raise BackupError("Too many backups were created in the same millisecond.")
            atomic_write_bytes(dest, data, sleep=self._sleep)
        except OSError as exc:
            raise BackupError(f"Could not write the backup: {exc}") from exc
        self._prune(folder)
        return dest

    def list(self, project_id: str) -> List[BackupInfo]:
        """Backups of ``project_id``, newest first."""
        return self._scan(self._folder(project_id), project_id)

    def restore(self, info: BackupInfo, dest: Path) -> Path:
        """Copy a backup to ``dest``. Never overwrites an existing file."""
        dest = Path(dest)
        if dest.exists():
            raise BackupError(f"'{dest.name}' already exists; choose a different name.")
        try:
            data = info.path.read_bytes()
            atomic_write_bytes(dest, data, sleep=self._sleep)
        except OSError as exc:
            raise BackupError(f"Could not restore the backup: {exc}") from exc
        return dest

    def _scan(self, folder: Path, project_id: str) -> List[BackupInfo]:
        try:
            names = sorted((p.name for p in folder.iterdir() if p.is_file()), reverse=True)
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise BackupError(f"Could not list backups: {exc}") from exc
        infos: List[BackupInfo] = []
        for name in names:
            match = _NAME_RE.match(name)
            if match:
                infos.append(BackupInfo(folder / name, project_id, match.group(1), match.group(3)))
        return infos

    def _prune(self, folder: Path) -> None:
        try:
            infos = self._scan(folder, folder.name)
        except BackupError:
            logger.warning("Could not list %s for pruning", folder, exc_info=True)
            return
        for old in infos[self._keep:]:
            try:
                old.path.unlink()
            except OSError:
                logger.warning("Could not delete old backup %s", old.path, exc_info=True)
