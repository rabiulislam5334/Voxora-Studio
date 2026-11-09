"""Step 2 -- disk stamps and rolling backups."""
from __future__ import annotations

import itertools
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.config import AppConfig
from app.persistence.backups import BackupError, BackupStore
from app.persistence.stamps import read_stamped, stamp_from_bytes, stamp_of_written


def _clock():
    base = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    counter = itertools.count()
    return lambda: base + timedelta(seconds=next(counter))


# ---------------------------------------------------------------- stamps


def test_only_the_hash_decides_whether_content_changed(tmp_path):
    f = tmp_path / "a.voxora"
    f.write_bytes(b"same bytes")
    data, first = read_stamped(f)
    os.utime(f, ns=(first.mtime_ns + 5_000_000_000,) * 2)  # touched, not changed
    _, touched = read_stamped(f)

    assert data == b"same bytes"
    assert touched.mtime_ns != first.mtime_ns
    assert touched.same_content(first)
    assert not stamp_from_bytes(b"other bytes").same_content(first)


def test_stamp_of_written_hashes_the_bytes_written(tmp_path):
    f = tmp_path / "a.voxora"
    f.write_bytes(b"abc")
    assert stamp_of_written(f, b"abc").sha256 == stamp_from_bytes(b"abc").sha256
    assert stamp_of_written(tmp_path / "missing", b"abc").mtime_ns == 0


# --------------------------------------------------------------- backups


def test_keeps_only_the_newest_five_backups_newest_first(tmp_path):
    store = BackupStore(tmp_path / "bk", keep=5, clock=_clock())
    for i in range(8):
        store.create_from_bytes("proj1", "episode", f"v{i}".encode())
    infos = store.list("proj1")

    assert len(infos) == 5
    assert [i.path.read_bytes() for i in infos] == [b"v7", b"v6", b"v5", b"v4", b"v3"]
    assert len(list((tmp_path / "bk" / "proj1").iterdir())) == 5


def test_two_backups_in_the_same_millisecond_get_distinct_ordered_names(tmp_path):
    fixed = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = BackupStore(tmp_path / "bk", clock=lambda: fixed)
    store.create_from_bytes("p", "s", b"first")
    store.create_from_bytes("p", "s", b"second")
    assert [i.path.read_bytes() for i in store.list("p")] == [b"second", b"first"]


def test_unsafe_characters_are_replaced_but_unicode_names_survive(tmp_path):
    store = BackupStore(tmp_path / "bk", clock=_clock())
    path = store.create_from_bytes("p", 'a:b?ভিডিও', b"x")
    assert "ভিডিও" in path.name
    assert ":" not in path.name and "?" not in path.name


def test_restore_copies_bytes_and_never_overwrites(tmp_path):
    store = BackupStore(tmp_path / "bk", clock=_clock())
    store.create_from_bytes("p", "s", b"payload")
    info = store.list("p")[0]

    restored = store.restore(info, tmp_path / "out" / "back.voxora")
    assert restored.read_bytes() == b"payload"
    with pytest.raises(BackupError, match="already exists"):
        store.restore(info, restored)
    assert restored.read_bytes() == b"payload"


def test_backup_failure_raises_backup_error(tmp_path):
    blocker = tmp_path / "bk"
    blocker.write_text("a file where the folder should be")
    with pytest.raises(BackupError):
        BackupStore(blocker, clock=_clock()).create_from_bytes("p", "s", b"x")


def test_pruning_failure_does_not_fail_the_backup(tmp_path, monkeypatch):
    store = BackupStore(tmp_path / "bk", keep=1, clock=_clock())
    store.create_from_bytes("p", "s", b"one")

    def deny(self, *args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", deny)
    created = store.create_from_bytes("p", "s", b"two")  # prune of "one" fails, backup still made
    monkeypatch.undo()

    assert created.read_bytes() == b"two"


def test_listing_unknown_project_is_empty_and_config_paths_are_not_created(tmp_path):
    assert BackupStore(tmp_path / "bk").list("nobody") == []
    config = AppConfig(root_dir=tmp_path)
    assert config.backups_dir == tmp_path / "userdata" / "backups"
    config.ensure_directories()
    assert not config.userdata_dir.exists()  # not created until a later step wires it up
