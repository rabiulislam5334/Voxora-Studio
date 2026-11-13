"""In-memory staleness and write-barrier control for snapshot commits.

This module decides **whether a snapshot job may still be committed**. It does
no file I/O, starts no threads and knows nothing about sessions or OS locks;
the snapshot store and worker that use it are a later step.

Why revisions, not sequence numbers
-----------------------------------
A payload is captured (serialized) and only later enqueued; a Save can happen
in between. A sequence number allocated at enqueue time says nothing about
which project *state* the payload holds. Every payload therefore carries the
project **revision** read in the same call that serialized it, and freshness is
decided by revision: a job is stale if ``job.revision <= barrier`` where the
barrier is the revision a successful Save wrote to disk.

Locks and invariants
--------------------
* ``write_mutex`` (outer) is held by whoever commits a snapshot generation
  for the whole commit; ``alloc_lock`` (inner) guards the small control state.
* Lock order is ``write_mutex`` -> ``alloc_lock`` only (enforced).
* ``epoch`` and ``barrier`` are written only while holding BOTH locks
  (enforced). Consequence: while a commit runs, the barrier and epoch cannot
  change, so a commit that passed its freshness check at the start can never
  publish after the barrier covering it became effective.
* No file I/O and no logging while holding ``alloc_lock``.

Deferred seal
-------------
``on_save_success`` waits at most ``seal_timeout_s`` for ``write_mutex``. If
the worker is busy it records a *pending* record (a hint that makes
not-yet-started jobs drop) instead of raising the barrier without the mutex;
the worker raises the barrier with ``apply_pending()`` when its commit ends.
The barrier is *effective* only when raised under ``write_mutex``.
"""
from __future__ import annotations

import enum
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.exceptions import SnapshotSequenceExhausted
from app.persistence.stamps import FileStamp

MAX_SNAPSHOT_SEQUENCE = 999_999_999_999


class SnapshotState(enum.Enum):
    NORMAL = "normal"
    RESTORING = "restoring"  # a project replacement is in progress: no captures


class EnqueueOutcome(enum.Enum):
    QUEUED = "queued"
    DEFERRED = "deferred"  # control is RESTORING; try again after it finishes
    STALE = "stale"  # the ticket belongs to a replaced project; nothing allocated


class CommitDecision(enum.Enum):
    COMMIT = "commit"
    DROP_EPOCH = "drop_epoch"
    DROP_REVISION = "drop_revision"
    DROP_SEQUENCE = "drop_sequence"


class SealOutcome(enum.Enum):
    SEALED = "sealed"  # barrier effective now
    DEFERRED = "deferred"  # recorded as pending; the worker seals later
    DISCARDED = "discarded"  # the record belongs to a replaced project


@dataclass(frozen=True)
class Ticket:
    epoch: int


@dataclass(frozen=True)
class Job:
    epoch: int
    seq: int
    revision: int
    payload: bytes


@dataclass(frozen=True)
class SaveRecord:
    """One verified successful Save: the state (``revision``) that is now on
    disk, where, and the stamp of that file. Pending records are replaced as a
    whole, so revision, path and stamp can never come from different saves."""

    epoch: int
    project_id: str
    revision: int
    path: Path
    stamp: FileStamp


class OwnedLock:
    """A non-reentrant lock that knows which thread owns it."""

    def __init__(self, name: str, on_block: Optional[Callable[[], None]] = None) -> None:
        self._name = name
        self._lock = threading.Lock()
        self._owner: Optional[int] = None
        self._on_block = on_block  # test hook: called just before blocking

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        if blocking and self._on_block is not None and self._lock.locked():
            self._on_block()
        got = self._lock.acquire(blocking, timeout) if blocking else self._lock.acquire(False)
        if got:
            self._owner = threading.get_ident()
        return got

    def release(self) -> None:
        if self._owner != threading.get_ident():
            raise RuntimeError(f"{self._name} released by a thread that does not own it")
        self._owner = None
        self._lock.release()

    def owned(self) -> bool:
        return self._owner == threading.get_ident()

    def __enter__(self) -> "OwnedLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class SnapshotControl:
    def __init__(
        self,
        *,
        seal_timeout_s: float = 2.0,
        replace_timeout_s: float = 3.0,
        on_write_blocked: Optional[Callable[[], None]] = None,
    ) -> None:
        self._seal_timeout = seal_timeout_s
        self._replace_timeout = replace_timeout_s
        self._alloc = OwnedLock("alloc_lock")
        self._write = OwnedLock("write_mutex", on_block=on_write_blocked)
        self._counter = 1
        self._epoch = 1
        self._barrier = -1
        self._pending: Optional[SaveRecord] = None
        self._state = SnapshotState.NORMAL
        self._prev_state = SnapshotState.NORMAL
        self._last_committed = 0

    # ----------------------------------------------------------- read access

    @property
    def epoch(self) -> int:
        with self._alloc:
            return self._epoch

    @property
    def barrier_revision(self) -> int:
        with self._alloc:
            return self._barrier

    @property
    def pending_record(self) -> Optional[SaveRecord]:
        with self._alloc:
            return self._pending

    @property
    def state(self) -> SnapshotState:
        with self._alloc:
            return self._state

    @property
    def last_committed(self) -> int:
        with self._alloc:
            return self._last_committed

    # ------------------------------------------------------- write_mutex API

    def acquire_write(self, timeout: Optional[float] = None) -> bool:
        """Take ``write_mutex``. ``timeout=None`` blocks, ``0`` never blocks."""
        if self._alloc.owned():
            raise RuntimeError("Lock order violation: write_mutex must be taken before alloc_lock")
        if timeout is None:
            return self._write.acquire(True)
        if timeout <= 0:
            return self._write.acquire(False)
        return self._write.acquire(True, timeout)

    def release_write(self) -> None:
        self._write.release()

    # --------------------------------------------------------------- capture

    def begin_capture(self) -> Optional[Ticket]:
        """Start a capture. Returns ``None`` while a replacement is running."""
        with self._alloc:
            if self._state is not SnapshotState.NORMAL:
                return None
            return Ticket(self._epoch)

    def enqueue(
        self,
        ticket: Ticket,
        payload: bytes,
        revision: int,
        sink: Optional[Callable[[Job], None]] = None,
    ):
        """Allocate a sequence for a captured payload. ``sink`` (optional)
        runs inside the critical section so queue order equals sequence order;
        it must not block or do I/O. Returns ``(outcome, job_or_None)``."""
        with self._alloc:
            if self._state is not SnapshotState.NORMAL:
                return EnqueueOutcome.DEFERRED, None
            if ticket.epoch != self._epoch:
                return EnqueueOutcome.STALE, None
            if self._counter > MAX_SNAPSHOT_SEQUENCE:
                raise SnapshotSequenceExhausted(
                    "Snapshot sequence limit reached (12 digits). No new snapshot was created."
                )
            job = Job(epoch=ticket.epoch, seq=self._counter, revision=revision, payload=payload)
            self._counter += 1
            if sink is not None:
                sink(job)
            return EnqueueOutcome.QUEUED, job

    def restore_sequence_state(
        self, *, highest_valid: int = 0, highest_seen: int = 0, restored_seq: int = 0
    ) -> int:
        """Restore the next sequence floor from an on-disk scan.

        Corrupt/orphan identifiers still count as seen so their numbers are
        never reused. Safe both during startup and while replacement already
        owns write_mutex.
        """
        values = (highest_valid, highest_seen, restored_seq)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Snapshot sequence values must be non-negative integers.")

        def apply() -> int:
            with self._alloc:
                maximum = max(values)
                self._counter = max(self._counter, maximum + 1)
                self._last_committed = max(self._last_committed, highest_valid)
                return self._counter

        if self._write.owned():
            return apply()
        with self._write:
            return apply()

    # ---------------------------------------------------------------- commit

    def decide_commit(self, job: Job) -> CommitDecision:
        """Freshness check at the start of a commit. Requires ``write_mutex``."""
        self._require_write()
        with self._alloc:
            if job.epoch != self._epoch:
                return CommitDecision.DROP_EPOCH
            pending = self._pending.revision if self._current_pending() else -1
            if job.revision <= max(self._barrier, pending):
                return CommitDecision.DROP_REVISION
            if job.seq <= self._last_committed:
                return CommitDecision.DROP_SEQUENCE
            return CommitDecision.COMMIT

    def note_committed(self, job: Job) -> None:
        """Record that ``job`` is now the current generation. Requires ``write_mutex``."""
        self._require_write()
        with self._alloc:
            if job.seq > self._last_committed:
                self._last_committed = job.seq

    # ------------------------------------------------------------------ save

    def on_save_success(self, record: SaveRecord) -> SealOutcome:
        """Record a verified Save before waiting for the commit mutex.

        Publishing the pending record first closes the hand-off race: a worker
        that acquires write_mutex immediately after another worker releases it
        must already see this Save's revision in decide_commit().
        """
        with self._alloc:
            if record.epoch != self._epoch:
                return SealOutcome.DISCARDED
            if self._pending is None or self._pending.epoch != self._epoch or record.revision > self._pending.revision:
                self._pending = record  # revision, path and stamp move together

        acquired = self.acquire_write(self._seal_timeout)
        if not acquired:
            # The worker may have released the mutex just as the timed wait
            # expired. Since the pending record is already visible, retry once
            # without waiting to seal it here if the mutex is now free.
            acquired = self.acquire_write(0)
        if acquired:
            try:
                self.apply_pending()
            finally:
                self.release_write()

        # A worker may have applied the pending record while we were waiting,
        # or may apply it later at the end of its current commit.
        with self._alloc:
            if record.epoch != self._epoch:
                return SealOutcome.DISCARDED
            sealed = self._barrier >= record.revision
        return SealOutcome.SEALED if sealed else SealOutcome.DEFERRED

    def apply_pending(self) -> Optional[SaveRecord]:
        """Raise the barrier from the pending record (worker, at the end of a
        job). Requires ``write_mutex``. Returns the record it applied."""
        self._require_write()
        with self._alloc:
            record = self._pending
            if record is None:
                return None
            if record.epoch != self._epoch:
                self._pending = None
                return None
            self._raise_barrier_locked(record.revision)
            return record

    def _seal_locked(self, record: SaveRecord) -> SealOutcome:
        with self._alloc:
            if record.epoch != self._epoch:
                return SealOutcome.DISCARDED
            self._raise_barrier_locked(record.revision)
            return SealOutcome.SEALED

    # ------------------------------------------------------- project replace

    def begin_replace(self, timeout: Optional[float] = None) -> bool:
        """Start replacing the project (Restore / Open / New). Captures and
        enqueues are refused from now on. Returns False (and changes nothing)
        if a replacement is already running or ``write_mutex`` cannot be taken
        in time. On True the caller holds ``write_mutex`` and must finish with
        ``commit_replace()`` or ``abort_replace()``."""
        with self._alloc:
            if self._state is SnapshotState.RESTORING:
                return False
            self._prev_state = self._state
            self._state = SnapshotState.RESTORING
        wait = self._replace_timeout if timeout is None else timeout
        if self.acquire_write(wait):
            return True
        with self._alloc:
            self._state = self._prev_state
        return False

    def commit_replace(self) -> None:
        """The new project is installed: bump the epoch (old tickets, jobs and
        records are now stale) and release ``write_mutex``. State stays
        RESTORING until ``end_replace()`` (after the UI refresh)."""
        self._require_write()
        with self._alloc:
            self._set_epoch_locked(self._epoch + 1)
            self._reset_barrier_locked()
        self.release_write()

    def abort_replace(self) -> None:
        self._require_write()
        with self._alloc:
            self._state = self._prev_state
        self.release_write()

    def end_replace(self) -> None:
        with self._alloc:
            if self._state is SnapshotState.RESTORING:
                self._state = SnapshotState.NORMAL

    # -------------------------------------------------------------- internals

    def _current_pending(self) -> bool:
        # caller holds alloc_lock
        return self._pending is not None and self._pending.epoch == self._epoch

    def _require_write(self) -> None:
        if not self._write.owned():
            raise RuntimeError("write_mutex must be held for this operation")

    def _require_both(self) -> None:
        if not (self._write.owned() and self._alloc.owned()):
            raise RuntimeError("barrier and epoch may only change while holding write_mutex and alloc_lock")

    def _raise_barrier_locked(self, revision: int) -> None:
        self._require_both()
        if revision > self._barrier:
            self._barrier = revision
        if self._pending is not None and self._pending.revision <= self._barrier:
            self._pending = None

    def _set_epoch_locked(self, epoch: int) -> None:
        self._require_both()
        self._epoch = epoch

    def _reset_barrier_locked(self) -> None:
        self._require_both()
        self._barrier = -1
        self._pending = None
