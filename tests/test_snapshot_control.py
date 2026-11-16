"""Step 2 -- revision-based staleness and the write barrier (no files, no workers).

The races are forced deterministically with Events; there are no stress loops.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.persistence.snapshot_control import (
    CommitDecision,
    EnqueueOutcome,
    SaveRecord,
    SealOutcome,
    SnapshotControl,
    SnapshotState,
)
from app.persistence.stamps import stamp_from_bytes


def _record(control, revision, tag="a"):
    return SaveRecord(
        epoch=control.epoch,
        project_id="proj",
        revision=revision,
        path=Path(f"/x/{tag}.voxora"),
        stamp=stamp_from_bytes(tag.encode()),
    )


def _queue(control, ticket, revision):
    outcome, job = control.enqueue(ticket, b"payload", revision)
    assert outcome is EnqueueOutcome.QUEUED
    return job


def _decide(control, job):
    assert control.acquire_write(0)
    try:
        return control.decide_commit(job)
    finally:
        control.release_write()


# --------------------------------------------------- the SaveMark race (A)


def test_old_payload_enqueued_after_a_save_is_dropped_by_revision_not_sequence():
    control = SnapshotControl()
    ticket = control.begin_capture()          # 1. capture begins ...
    old_payload_revision = 8                  # 2. ... and serializes state at revision 8
    # edits continue (revision 9), the user saves, the save is sealed:
    assert control.on_save_success(_record(control, 9)) is SealOutcome.SEALED
    # 3. the old payload is enqueued only now and receives a HIGHER sequence:
    stale = _queue(control, ticket, old_payload_revision)
    newer = _queue(control, control.begin_capture(), 10)   # captured after the save

    assert stale.seq < newer.seq
    assert _decide(control, stale) is CommitDecision.DROP_REVISION   # survives by sequence, dies by revision
    assert _decide(control, newer) is CommitDecision.COMMIT


def test_pending_seal_also_drops_not_yet_started_stale_jobs():
    control = SnapshotControl(seal_timeout_s=0.05)
    old = _queue(control, control.begin_capture(), 4)
    assert control.acquire_write(0)           # the worker is mid-commit
    try:
        assert control.on_save_success(_record(control, 6)) is SealOutcome.DEFERRED
        assert control.barrier_revision == -1  # NOT raised without the mutex
        assert control.decide_commit(old) is CommitDecision.DROP_REVISION  # but the hint drops it
    finally:
        control.release_write()


# ---------------------------------------- strict seal (waits for the commit)


def test_strict_seal_waits_for_an_inflight_commit_then_raises_the_barrier():
    blocked = threading.Event()
    control = SnapshotControl(on_write_blocked=blocked.set)
    assert control.acquire_write(0)           # an in-flight commit holds write_mutex
    result = {}
    saver = threading.Thread(target=lambda: result.update(outcome=control.on_save_success(_record(control, 9))))
    saver.start()

    assert blocked.wait(5)                    # the Save is now waiting for the mutex
    assert control.barrier_revision == -1     # and has NOT raised the barrier
    control.release_write()                   # the commit ends
    saver.join(5)

    assert result["outcome"] is SealOutcome.SEALED
    assert control.barrier_revision == 9


# ------------- the exact interleaving: pause after validation, before pointer


def test_deferred_seal_cannot_raise_the_barrier_while_a_commit_is_about_to_publish():
    control = SnapshotControl(seal_timeout_s=0.2)
    job = _queue(control, control.begin_capture(), 5)
    log = []

    assert control.acquire_write(0)           # worker: commit begins ...
    assert control.decide_commit(job) is CommitDecision.COMMIT   # ... freshness check passes
    log.append("validated")                   # payload + metadata published and validated
    # --- paused here: after validation, BEFORE the pointer write ---

    outcome = {}
    saver = threading.Thread(target=lambda: outcome.update(o=control.on_save_success(_record(control, 7))))
    saver.start()
    saver.join(5)                             # times out after 0.2 s (mutex is held)

    assert outcome["o"] is SealOutcome.DEFERRED
    assert control.barrier_revision == -1     # the barrier did not change under the committing worker
    assert control.pending_record is not None

    log.append("pointer_write")               # the worker finishes: it may still publish (barrier not effective)
    control.note_committed(job)
    applied = control.apply_pending()         # end of the job, still under write_mutex
    log.append("barrier_effective")
    control.release_write()

    assert log == ["validated", "pointer_write", "barrier_effective"]
    assert applied.revision == 7 and control.barrier_revision == 7 and control.pending_record is None

    # from now on nothing at or below the barrier can commit
    later_stale = _queue(control, control.begin_capture(), 7)
    later_new = _queue(control, control.begin_capture(), 8)
    assert _decide(control, later_stale) is CommitDecision.DROP_REVISION
    assert _decide(control, later_new) is CommitDecision.COMMIT


# ------------------------------------------------------- pending records


def test_pending_record_is_replaced_as_one_object_and_never_by_an_older_one():
    control = SnapshotControl(seal_timeout_s=0.02)
    assert control.acquire_write(0)
    try:
        r5, r8, r6 = _record(control, 5, "five"), _record(control, 8, "eight"), _record(control, 6, "six")
        control.on_save_success(r5)
        assert control.pending_record is r5
        control.on_save_success(r8)
        assert control.pending_record is r8            # revision, path and stamp all from the same save
        control.on_save_success(r6)
        assert control.pending_record is r8            # an older record never replaces a newer one
        assert control.pending_record.stamp == stamp_from_bytes(b"eight")
    finally:
        control.release_write()


def test_record_from_a_replaced_project_is_discarded():
    control = SnapshotControl(seal_timeout_s=0.02)
    old = _record(control, 5)
    assert control.begin_replace(timeout=1)
    control.commit_replace()
    control.end_replace()

    assert control.on_save_success(old) is SealOutcome.DISCARDED
    assert control.barrier_revision == -1


def test_stale_epoch_record_is_discarded_on_the_deferred_path_too():
    control = SnapshotControl(seal_timeout_s=0.02)
    old = _record(control, 5)                      # belongs to the project about to be replaced
    assert control.begin_replace(timeout=1)
    control.commit_replace()                       # epoch bumped, write_mutex released
    control.end_replace()

    assert control.acquire_write(0)                # worker busy, so a Save would defer
    try:
        assert control.on_save_success(old) is SealOutcome.DISCARDED
    finally:
        control.release_write()
    assert control.pending_record is None and control.barrier_revision == -1


# ------------------------------------------------ project replacement


def test_replacement_blocks_captures_until_the_end_and_makes_old_tickets_stale():
    control = SnapshotControl()
    old_ticket = control.begin_capture()
    counter_before = _queue(control, old_ticket, 1).seq

    assert control.begin_replace(timeout=1)
    assert control.state is SnapshotState.RESTORING
    assert control.begin_capture() is None                                   # no new captures
    assert control.enqueue(old_ticket, b"x", 2)[0] is EnqueueOutcome.DEFERRED
    control.commit_replace()                                                 # project installed, epoch bumped
    assert control.begin_capture() is None                                   # still blocked during the UI refresh
    control.end_replace()

    assert control.state is SnapshotState.NORMAL
    assert control.enqueue(old_ticket, b"x", 3)[0] is EnqueueOutcome.STALE   # nothing allocated for it
    new_job = _queue(control, control.begin_capture(), 4)
    assert new_job.epoch == old_ticket.epoch + 1 and new_job.seq == counter_before + 1
    assert control.barrier_revision == -1 and control.pending_record is None


def test_replacement_that_cannot_get_the_mutex_changes_nothing():
    control = SnapshotControl()
    ticket = control.begin_capture()
    held, release = threading.Event(), threading.Event()

    def worker():
        control.acquire_write()
        held.set()
        release.wait(5)
        control.release_write()

    t = threading.Thread(target=worker)
    t.start()
    assert held.wait(5)

    assert control.begin_replace(timeout=0.1) is False
    assert control.state is SnapshotState.NORMAL and control.epoch == 1
    assert control.enqueue(ticket, b"x", 1)[0] is EnqueueOutcome.QUEUED     # old ticket still valid
    release.set()
    t.join(5)


def test_second_replacement_is_refused_and_abort_restores_the_previous_state():
    control = SnapshotControl()
    assert control.begin_replace(timeout=1)
    assert control.begin_replace(timeout=1) is False
    control.abort_replace()
    assert control.state is SnapshotState.NORMAL and control.epoch == 1


def test_late_enqueued_older_capture_cannot_regress_committed_revision():
    control = SnapshotControl()
    older_ticket = control.begin_capture()
    newer_ticket = control.begin_capture()

    # The newer capture finishes serialization/enqueue first and gets the
    # lower sequence. The older capture is enqueued later with a higher seq.
    newer = _queue(control, newer_ticket, 11)
    older = _queue(control, older_ticket, 10)

    assert newer.seq < older.seq
    assert control.acquire_write(0)
    try:
        assert control.decide_commit(newer) is CommitDecision.COMMIT
        control.note_committed(newer)
        assert control.decide_commit(older) is CommitDecision.DROP_REVISION
    finally:
        control.release_write()


# ------------------------------------------------------- sequences / locks


def test_sequences_are_unique_under_concurrency_and_sink_order_matches():
    control = SnapshotControl()
    ticket = control.begin_capture()
    sunk, jobs, guard = [], [], threading.Lock()

    def producer():
        for i in range(100):
            outcome, job = control.enqueue(ticket, b"p", i, sink=lambda j: sunk.append(j.seq))
            with guard:
                jobs.append(job.seq)

    threads = [threading.Thread(target=producer) for _ in range(8)]
    [t.start() for t in threads]
    [t.join(10) for t in threads]

    assert len(jobs) == 800 and len(set(jobs)) == 800
    assert sunk == sorted(sunk)               # queue order == sequence order


def test_older_sequence_is_dropped_after_a_newer_one_committed():
    control = SnapshotControl()
    t = control.begin_capture()
    first, second = _queue(control, t, 1), _queue(control, t, 2)
    assert control.acquire_write(0)
    try:
        control.note_committed(second)
        assert control.decide_commit(first) is CommitDecision.DROP_SEQUENCE
    finally:
        control.release_write()


def test_lock_discipline_is_enforced():
    control = SnapshotControl()
    with pytest.raises(RuntimeError, match="write_mutex"):
        control.decide_commit(_queue(control, control.begin_capture(), 1))
    with pytest.raises(RuntimeError, match="write_mutex and alloc_lock"):
        control._raise_barrier_locked(5)       # barrier cannot change without both locks
    with pytest.raises(RuntimeError, match="write_mutex and alloc_lock"):
        control._set_epoch_locked(9)
    with control._alloc:
        with pytest.raises(RuntimeError, match="Lock order"):
            control.acquire_write()            # alloc_lock -> write_mutex is forbidden
    assert control.barrier_revision == -1 and control.epoch == 1
