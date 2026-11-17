from __future__ import annotations

import errno
import os
import shutil
import time
from pathlib import Path

from app.core.logger import get_logger

logger = get_logger("cache.temp_cleanup")

# Dead-owner directories are retained for a day before deletion. Legacy
# directories without an ownership marker use a much longer grace period.
_OWNER_STALE_SECONDS = 24 * 60 * 60
_LEGACY_STALE_SECONDS = 7 * 24 * 60 * 60


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError as exc:
        if exc.errno == errno.ESRCH or getattr(exc, "winerror", None) == 87:
            return False
        # Unknown OS errors are treated conservatively: do not delete.
        return True


def cleanup_stale_production_dirs(root: Path, *, now: float | None = None) -> int:
    """Remove only old production workdirs whose owner is known to be dead.

    Active PIDs are never removed. Unknown/corrupt ownership markers are
    retained. Legacy unmarked workdirs receive a seven-day grace period.
    Shared cache directories are intentionally not scanned: another render
    may be writing a uniquely named cache .part file there.
    """
    root = Path(root)
    now = time.time() if now is None else float(now)
    removed = 0
    try:
        candidates = list(root.glob("production_*"))
    except OSError as exc:
        logger.warning("Could not scan production temp directory %s: %s", root, exc)
        return 0

    for folder in candidates:
        try:
            if folder.is_symlink() or not folder.is_dir():
                continue
            marker = folder / ".voxora-owner"
            if marker.exists():
                fields = marker.read_text(encoding="ascii").strip().split()
                if len(fields) != 2:
                    continue
                pid, started = int(fields[0]), float(fields[1])
                if _pid_is_alive(pid):
                    continue
                if now - started < _OWNER_STALE_SECONDS:
                    continue
            else:
                if now - folder.stat().st_mtime < _LEGACY_STALE_SECONDS:
                    continue
            shutil.rmtree(folder)
            removed += 1
        except (OSError, ValueError) as exc:
            logger.warning("Could not clean stale production directory %s: %s", folder, exc)
    return removed
