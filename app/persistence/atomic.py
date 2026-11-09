"""Crash-safe file replacement.

A write goes to a temp file in the *same directory* as the target (so the
final rename never crosses a filesystem), is flushed and fsynced, and only
then replaced over the target with ``Path.replace``. A crash or power loss at
any point leaves either the old file or the complete new one -- never a
half-written file.

Retry policy (Windows): the final replace can fail with ``PermissionError``
while antivirus, an indexer or a sync client briefly holds the target. Exactly
``len(RETRY_DELAYS_S) + 1`` = **4 attempts** are made, sleeping 0.05 s, 0.15 s
and 0.40 s between them (0.60 s worst case). Only ``PermissionError`` is
retried; every other ``OSError`` fails on the first attempt.

``commit`` deliberately calls ``Path.replace`` (not ``os.replace``) so that
tests can inject failures at that single point.

Nothing here knows about projects, locks or sessions.
"""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

TEMP_PREFIX = ".voxora_tmp_"
TEMP_SUFFIX = ".json"

# Delays between consecutive attempts of the final replace (4 attempts total).
RETRY_DELAYS_S: Tuple[float, ...] = (0.05, 0.15, 0.40)


class StagedWrite:
    """A fully written, fsynced temp file waiting to be committed.

    Use as a context manager: if the block ends without a successful
    ``commit()`` (an exception, a conflict, a failed replace) the temp file is
    removed, so a failed save never leaves debris behind.
    """

    def __init__(
        self,
        target: Path,
        tmp_path: Path,
        sleep: Callable[[float], None],
        retry_delays: Sequence[float],
    ) -> None:
        self._target = target
        self._tmp = tmp_path
        self._sleep = sleep
        self._delays = tuple(retry_delays)
        self._finished = False

    @property
    def tmp_path(self) -> Path:
        return self._tmp

    @property
    def target(self) -> Path:
        return self._target

    def commit(self) -> None:
        """Replace the target with the staged file (4 attempts, see module doc)."""
        if self._finished:
            raise RuntimeError("This staged write was already committed.")
        attempts = len(self._delays) + 1
        for attempt in range(attempts):
            try:
                self._tmp.replace(self._target)
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                self._sleep(self._delays[attempt])
            else:
                self._finished = True
                return

    def discard(self) -> None:
        """Remove the temp file (best effort; safe to call more than once)."""
        try:
            self._tmp.unlink(missing_ok=True)
        except OSError:
            pass  # nothing more can be done; a leftover temp file is harmless

    def __enter__(self) -> "StagedWrite":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._finished:
            self.discard()


def stage_write(
    target: Path,
    data: bytes,
    *,
    sleep: Callable[[float], None] = time.sleep,
    retry_delays: Sequence[float] = RETRY_DELAYS_S,
) -> StagedWrite:
    """Write ``data`` to a temp file next to ``target`` and fsync it."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent), prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return StagedWrite(target, tmp_path, sleep, retry_delays)


def atomic_write_bytes(
    target: Path,
    data: bytes,
    *,
    sleep: Callable[[float], None] = time.sleep,
    retry_delays: Sequence[float] = RETRY_DELAYS_S,
) -> None:
    """Convenience: stage and commit in one call."""
    with stage_write(target, data, sleep=sleep, retry_delays=retry_delays) as staged:
        staged.commit()
