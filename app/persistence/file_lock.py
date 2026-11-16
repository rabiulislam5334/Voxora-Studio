"""Cross-process advisory lock for one Voxora project file.

The lock file is intentionally persistent. Deleting it after unlock is unsafe:
another process may already have opened the same inode while a third creates a
new one. The operating system releases the lock automatically if a process
exits or crashes.

This coordinates cooperating Voxora processes running under the same OS user account on the same machine. It cannot
prevent unrelated programs or remote machines from writing the project file;
the repository's disk-stamp checks remain necessary.
"""
from __future__ import annotations

import errno
import getpass
import hashlib
import math
import os
import tempfile
import time
from pathlib import Path
from typing import BinaryIO

from app.core.exceptions import ProjectLockError

_DEFAULT_TIMEOUT_S = 15.0
_RETRY_INTERVAL_S = 0.05


class ProjectFileLock:
    """Exclusive advisory lock keyed by the canonical project path.

    Uses the Windows byte-range locking API on Windows and flock on POSIX.
    A finite timeout prevents a stuck peer from freezing the UI forever.
    """

    def __init__(self, target: Path, *, timeout_s: float = _DEFAULT_TIMEOUT_S) -> None:
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise TypeError("timeout_s must be a finite positive number")
        if not math.isfinite(float(timeout_s)) or timeout_s <= 0:
            raise ValueError("timeout_s must be a finite number greater than zero")
        self.target = Path(target)
        canonical = os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(self.target))))
        key = hashlib.sha256(os.fsencode(canonical)).hexdigest()
        lock_root = Path(tempfile.gettempdir()) / f"voxora-studio-{getpass.getuser()}" / "project-locks"
        self.lock_path = lock_root / f"{key}.lock"
        self.timeout_s = float(timeout_s)
        self._handle: BinaryIO | None = None
        self._windows = os.name == "nt"

    def __enter__(self) -> "ProjectFileLock":
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.lock_path, "a+b")
        except OSError as exc:
            raise ProjectLockError(
                f"Could not prepare the save lock for '{self.target.name}': {exc}"
            ) from exc
        try:
            if self._windows:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(bytes(1))
                    handle.flush()
            deadline = time.monotonic() + self.timeout_s
            while True:
                try:
                    self._try_lock(handle)
                    self._handle = handle
                    return self
                except OSError as exc:
                    if not self._is_contention(exc):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ProjectLockError(
                            f"Could not acquire the save lock for '{self.target.name}' "
                            f"within {self.timeout_s:g} seconds. Another Voxora instance "
                            "may still be saving this project. Please try again."
                        ) from exc
                    time.sleep(min(_RETRY_INTERVAL_S, remaining))
        except BaseException:
            handle.close()
            raise

    def _try_lock(self, handle: BinaryIO) -> None:
        if self._windows:
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _is_contention(self, exc: OSError) -> bool:
        if not self._windows:
            return isinstance(exc, BlockingIOError) or exc.errno in (errno.EACCES, errno.EAGAIN)
        return exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK, 13, 36)

    def __exit__(self, exc_type, exc, tb) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            if self._windows:
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
