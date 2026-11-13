from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.exceptions import ProjectError, SnapshotSequenceExhausted
from app.persistence.snapshot_control import (
    CommitDecision,
    EnqueueOutcome,
    SaveRecord,
    SealOutcome,
    SnapshotControl,
)
from app.persistence.snapshot_control import MAX_SNAPSHOT_SEQUENCE
from app.persistence.snapshots import SnapshotStore
from app.persistence.stamps import read_stamped, stamp_from_bytes


def _queued(control: SnapshotControl, revision: int, payload: bytes = b"snapshot"):
    ticket = control.begin_capture()
    outcome, job = control.enqueue(ticket, payload, revision)
    assert outcome is EnqueueOutcome.QUEUED
    return job


def _commit(store: SnapshotStore, control: SnapshotControl, revision: int, payload=b"snapshot"):
    job = _queued(control, revision, payload)
    assert store.commit(job) is CommitDecision.COMMIT
    return job


def test_snapshot_store_is_disabled_by_default_and_writes_nothing(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control)
    job = _queued(control, 1)
    with pytest.raises(RuntimeError, match="disabled"):
        store.commit(job)
    assert not (tmp_path / "session").exists()


def test_commit_publishes_immutable_pair_and_current_pointer(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _commit(store, control, 7, b"project state")
    payload = tmp_path / "session" / f"snapshot-{job.seq:012d}.json"
    metadata = tmp_path / "session" / f"snapshot-{job.seq:012d}.meta.json"
    pointer = json.loads((tmp_path / "session" / "current.json").read_text())

    assert payload.read_bytes() == b"project state"
    assert json.loads(metadata.read_text())["sha256"]
    assert pointer == {"seq": job.seq, "epoch": job.epoch, "revision": 7}
    generation = store.load_generation(job.seq)
    assert generation.payload == b"project state" and generation.revision == 7


def test_scan_uses_generations_not_current_pointer_as_authority(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _commit(store, control, 1)
    (tmp_path / "session" / "current.json").write_text("{broken", encoding="utf-8")

    scan = store.scan()
    assert [item.seq for item in scan.generations] == [job.seq]
    assert scan.current is None
    assert scan.highest_valid == job.seq


def test_corrupt_orphan_counts_as_seen_and_sequence_is_never_reused(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "snapshot-000000000009.json").write_bytes(b"orphan")
    control = SnapshotControl()
    store = SnapshotStore(session, control, enabled=True)
    scan = store.scan()
    assert scan.highest_seen == 9 and scan.highest_valid == 0
    job = _queued(control, 1)
    assert job.seq == 10


def test_payload_metadata_mismatch_is_not_a_valid_generation(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _commit(store, control, 1)
    meta = tmp_path / "session" / f"snapshot-{job.seq:012d}.meta.json"
    data = json.loads(meta.read_text())
    data["sha256"] = "0" * 64
    meta.write_text(json.dumps(data), encoding="utf-8")

    scan = store.scan()
    assert scan.generations == ()
    assert scan.highest_seen == job.seq
    with pytest.raises(ProjectError, match="missing or invalid"):
        store.load_generation(job.seq)


def test_pointer_failure_keeps_fully_validated_generation_recoverable(tmp_path, monkeypatch):
    import app.persistence.snapshots as module

    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _queued(control, 1, b"recoverable")
    original = module.atomic_write_bytes
    calls = 0

    def fail_pointer(path, data, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("pointer disk failure")
        return original(path, data, **kwargs)

    monkeypatch.setattr(module, "atomic_write_bytes", fail_pointer)
    with pytest.raises(ProjectError, match="Could not commit snapshot"):
        store.commit(job)

    assert store.load_generation(job.seq).payload == b"recoverable"
    assert not (tmp_path / "session" / "current.json").exists()


def test_metadata_write_failure_removes_only_unvalidated_payload(tmp_path, monkeypatch):
    import app.persistence.snapshots as module

    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _queued(control, 1)
    calls = 0

    def fail_metadata(path, data, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("metadata disk failure")
        return module.atomic_write_bytes_original(path, data, **kwargs)

    module.atomic_write_bytes_original = module.atomic_write_bytes
    monkeypatch.setattr(module, "atomic_write_bytes", fail_metadata)
    with pytest.raises(ProjectError):
        store.commit(job)
    assert not (tmp_path / "session" / f"snapshot-{job.seq:012d}.json").exists()
    assert not (tmp_path / "session" / f"snapshot-{job.seq:012d}.meta.json").exists()


def test_retention_keeps_newest_three_per_epoch_and_never_prunes_old_epochs(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True, retention=3)
    old_epoch = control.epoch
    old_jobs = [_commit(store, control, i + 1, f"old-{i}".encode()) for i in range(4)]
    assert control.begin_replace(timeout=1)
    control.commit_replace()
    control.end_replace()
    new_jobs = [_commit(store, control, i + 10, f"new-{i}".encode()) for i in range(4)]

    valid = store.scan().generations
    old_valid = [item for item in valid if item.epoch == old_epoch]
    new_valid = [item for item in valid if item.epoch == control.epoch]
    assert len(old_valid) == 3
    assert len(new_valid) == 3
    assert {item.seq for item in old_valid}.issuperset({job.seq for job in old_jobs[-3:]})
    assert {item.seq for item in new_valid}.issuperset({job.seq for job in new_jobs[-3:]})


def test_save_seal_drops_covered_pointer_and_cleanup_checks_disk_stamp(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _commit(store, control, 4)
    project_file = tmp_path / "project.voxora"
    project_file.write_bytes(b"saved project")
    _, stamp = read_stamped(project_file)
    record = SaveRecord(control.epoch, "project", 4, project_file, stamp)

    assert store.seal_save(record) is SealOutcome.SEALED
    assert not (tmp_path / "session" / "current.json").exists()

    project_file.write_bytes(b"changed externally")
    assert store.cleanup_after_save(record) is False
    assert store.load_generation(job.seq).payload == b"snapshot"


def test_verified_save_cleanup_removes_covered_generation(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _commit(store, control, 4)
    project_file = tmp_path / "project.voxora"
    project_file.write_bytes(b"saved")
    _, stamp = read_stamped(project_file)
    record = SaveRecord(control.epoch, "project", 4, project_file, stamp)
    assert store.seal_save(record) is SealOutcome.SEALED
    assert store.cleanup_after_save(record) is True
    assert not (tmp_path / "session" / f"snapshot-{job.seq:012d}.json").exists()
    assert not (tmp_path / "session" / f"snapshot-{job.seq:012d}.meta.json").exists()


def test_cleanup_removes_pointer_before_generation_files(tmp_path, monkeypatch):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    job = _commit(store, control, 2)
    project_file = tmp_path / "project.voxora"
    project_file.write_bytes(b"saved")
    _, stamp = read_stamped(project_file)
    record = SaveRecord(control.epoch, "project", 2, project_file, stamp)
    control.on_save_success(record)  # leave pointer for the cleanup phase to invalidate

    removed = []
    original = Path.unlink

    def record_unlink(path, *args, **kwargs):
        removed.append(path.name)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", record_unlink)
    store.cleanup_after_save(record)
    assert removed.index("current.json") < removed.index(f"snapshot-{job.seq:012d}.meta.json")
    assert removed.index(f"snapshot-{job.seq:012d}.meta.json") < removed.index(f"snapshot-{job.seq:012d}.json")


def test_explicit_discard_removes_pointer_first_and_only_selected_epoch(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    old = _commit(store, control, 1)
    assert control.begin_replace(timeout=1)
    control.commit_replace()
    control.end_replace()
    current = _commit(store, control, 2)

    assert store.discard_epoch(old.epoch) == 1
    scan = store.scan()
    assert [item.seq for item in scan.generations] == [current.seq]
    assert scan.current.seq == current.seq


def test_scan_can_run_while_replacement_already_owns_write_mutex(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    _commit(store, control, 1)
    assert control.begin_replace(timeout=1)
    try:
        assert store.scan().highest_valid == 1
    finally:
        control.abort_replace()


def test_snapshot_sequence_exhaustion_is_explicit():
    control = SnapshotControl()
    control.restore_sequence_state(highest_seen=MAX_SNAPSHOT_SEQUENCE)
    ticket = control.begin_capture()
    with pytest.raises(SnapshotSequenceExhausted):
        control.enqueue(ticket, b"never write", 1)


def test_stale_revision_is_rejected_even_when_sequence_is_newer(tmp_path):
    control = SnapshotControl()
    store = SnapshotStore(tmp_path / "session", control, enabled=True)
    project_file = tmp_path / "project.voxora"
    project_file.write_bytes(b"saved")
    _, stamp = read_stamped(project_file)
    record = SaveRecord(control.epoch, "project", 5, project_file, stamp)
    assert store.seal_save(record) is SealOutcome.SEALED

    stale = _queued(control, 5)
    assert store.commit(stale) is CommitDecision.DROP_REVISION
