"""Step 2 -- atomic writer: failures keep the original, retry policy is exact."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.persistence.atomic import RETRY_DELAYS_S, atomic_write_bytes, stage_write


def _names(folder: Path):
    return sorted(p.name for p in folder.iterdir())


def test_failed_replace_keeps_original_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / "p.voxora"
    target.write_bytes(b"old")

    def boom(self, *args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(OSError, match="simulated"):
        atomic_write_bytes(target, b"new")
    monkeypatch.undo()

    assert target.read_bytes() == b"old"
    assert _names(tmp_path) == ["p.voxora"]  # no temp debris


def test_permission_error_is_attempted_exactly_four_times_with_exact_delays(tmp_path, monkeypatch):
    target = tmp_path / "p.voxora"
    target.write_bytes(b"old")
    calls, delays = [], []

    def locked(self, *args, **kwargs):
        calls.append(1)
        raise PermissionError("locked by antivirus")

    monkeypatch.setattr(Path, "replace", locked)
    with pytest.raises(PermissionError):
        atomic_write_bytes(target, b"new", sleep=delays.append)
    monkeypatch.undo()

    assert RETRY_DELAYS_S == (0.05, 0.15, 0.40)
    assert len(calls) == 4
    assert delays == [0.05, 0.15, 0.40]
    assert target.read_bytes() == b"old"
    assert _names(tmp_path) == ["p.voxora"]


def test_permission_error_then_success_writes_new_content(tmp_path, monkeypatch):
    target = tmp_path / "p.voxora"
    target.write_bytes(b"old")
    original = Path.replace
    calls, delays = [], []

    def flaky(self, destination):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("briefly locked")
        return original(self, destination)

    monkeypatch.setattr(Path, "replace", flaky)
    atomic_write_bytes(target, b"new", sleep=delays.append)
    monkeypatch.undo()

    assert target.read_bytes() == b"new"
    assert delays == [0.05, 0.15]
    assert _names(tmp_path) == ["p.voxora"]


def test_other_oserror_is_not_retried(tmp_path, monkeypatch):
    target = tmp_path / "p.voxora"
    calls, delays = [], []

    def broken(self, *args, **kwargs):
        calls.append(1)
        raise OSError("no space left")

    monkeypatch.setattr(Path, "replace", broken)
    with pytest.raises(OSError):
        atomic_write_bytes(target, b"new", sleep=delays.append)
    monkeypatch.undo()

    assert len(calls) == 1 and delays == []


def test_temp_file_is_fsynced_before_it_is_replaced(tmp_path, monkeypatch):
    target = tmp_path / "p.voxora"
    events = []
    real_fsync, real_replace = os.fsync, Path.replace

    monkeypatch.setattr(os, "fsync", lambda fd: (events.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(Path, "replace", lambda self, dest: (events.append("replace"), real_replace(self, dest))[1])
    atomic_write_bytes(target, b"data")
    monkeypatch.undo()

    assert events == ["fsync", "replace"]


def test_writes_exact_bytes_and_creates_parent_folders(tmp_path):
    target = tmp_path / "বাংলা ফোল্ডার" / "sub" / "ভিডিও.voxora"
    payload = "আমার প্রজেক্ট".encode("utf-8")
    atomic_write_bytes(target, payload)
    assert target.read_bytes() == payload
    assert _names(target.parent) == ["ভিডিও.voxora"]


def test_staged_write_discards_temp_when_never_committed(tmp_path):
    target = tmp_path / "p.voxora"
    with stage_write(target, b"x") as staged:
        assert staged.tmp_path.exists()
    assert _names(tmp_path) == []
