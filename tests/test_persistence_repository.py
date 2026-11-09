"""Step 2 -- repository: format, save ordering, conflicts, backups, Defect 1."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.core.exceptions import ProjectBackupError, ProjectConflictError, ProjectError
from app.models.project import Project
from app.models.scene import Scene
from app.persistence.backups import BackupStore
from app.persistence.repository import JsonProjectRepository
from app.persistence.stamps import stamp_from_bytes
from app.projects.manager import ProjectManager
from app.projects.serializer import project_to_dict


def _project(name="Episode", text="Hello"):
    project = Project(name=name)
    project.scenes.append(Scene(title="Scene", text=text, order=0))
    return project


def _names(folder: Path):
    return sorted(p.name for p in folder.iterdir())


# ------------------------------------------------------------------ format / load


def test_serialize_is_json_of_the_project_with_unescaped_unicode():
    repo = JsonProjectRepository()
    project = _project("প্রজেক্ট", "আমি ভালো আছি।")
    data = repo.serialize(project)
    text = data.decode("utf-8")

    assert "প্রজেক্ট" in text and "\\u09" not in text
    assert json.loads(text) == json.loads(json.dumps(project_to_dict(project)))
    assert not data.startswith(b"\xef\xbb\xbf")  # no BOM


def test_load_invalid_utf8_raises_project_error_not_unicode_error(tmp_path):
    f = tmp_path / "bad.voxora"
    f.write_bytes(b'{"name": "\xff\xfe"}')
    with pytest.raises(ProjectError, match="not valid UTF-8"):
        JsonProjectRepository().load(f)


def test_load_returns_the_stamp_of_the_bytes_read(tmp_path):
    repo = JsonProjectRepository()
    f = tmp_path / "p.voxora"
    repo.save(_project(), f)
    result = repo.load(f)
    assert result.stamp.sha256 == stamp_from_bytes(f.read_bytes()).sha256
    assert result.project.name == "Episode"


# ------------------------------------------------------------------------- save


def test_save_new_file_returns_stamp_of_written_bytes_and_no_backup(tmp_path):
    store = BackupStore(tmp_path / "bk")
    repo = JsonProjectRepository(store)
    f = tmp_path / "proj" / "p.voxora"
    outcome = repo.save(_project(), f)

    assert outcome.backup_path is None
    assert outcome.stamp.sha256 == stamp_from_bytes(f.read_bytes()).sha256
    assert _names(f.parent) == ["p.voxora"]
    assert store.list(_project().id) == []


def test_overwrite_backs_up_the_previous_bytes_before_replacing(tmp_path):
    store = BackupStore(tmp_path / "bk")
    repo = JsonProjectRepository(store)
    f = tmp_path / "p.voxora"
    project = _project()
    first = repo.save(project, f)
    first_bytes = f.read_bytes()

    project.scenes[0].text = "Changed"
    second = repo.save(project, f, expected_stamp=first.stamp)

    backups = store.list(project.id)
    assert len(backups) == 1 and backups[0].path.read_bytes() == first_bytes
    assert second.backup_path == backups[0].path
    assert "Changed" in f.read_text(encoding="utf-8")


def test_external_change_is_a_conflict_and_nothing_is_written(tmp_path):
    store = BackupStore(tmp_path / "bk")
    repo = JsonProjectRepository(store)
    f = tmp_path / "p.voxora"
    project = _project()
    first = repo.save(project, f)

    f.write_bytes(b'{"name": "edited elsewhere"}')  # another program
    external = f.read_bytes()
    project.scenes[0].text = "my edit"
    with pytest.raises(ProjectConflictError, match="Save As"):
        repo.save(project, f, expected_stamp=first.stamp)

    assert f.read_bytes() == external
    assert _names(tmp_path) == ["p.voxora"]  # no temp file, and no backup folder was even created
    assert store.list(project.id) == []  # the conflict is detected before any backup


def test_same_size_but_different_content_is_still_a_conflict(tmp_path):
    repo = JsonProjectRepository()
    f = tmp_path / "p.voxora"
    project = _project()
    first = repo.save(project, f)

    original = f.read_bytes()
    external = original.replace(b"Hello", b"Jello")  # one byte changed, identical length
    assert len(external) == len(original) and external != original
    f.write_bytes(external)

    with pytest.raises(ProjectConflictError):
        repo.save(project, f, expected_stamp=first.stamp)
    assert f.read_bytes() == external


def test_same_bytes_with_a_new_mtime_is_not_a_conflict(tmp_path):
    repo = JsonProjectRepository()
    f = tmp_path / "p.voxora"
    project = _project()
    first = repo.save(project, f)
    os.utime(f, ns=(first.stamp.mtime_ns + 9_000_000_000,) * 2)  # sync tool touched it
    repo.save(project, f, expected_stamp=first.stamp)  # must not raise


def test_a_write_between_backup_and_replace_is_caught_by_the_second_check(tmp_path, monkeypatch):
    store = BackupStore(tmp_path / "bk")
    repo = JsonProjectRepository(store)
    f = tmp_path / "p.voxora"
    project = _project()
    first = repo.save(project, f)

    real_create = BackupStore.create_from_bytes

    def create_then_other_writer_lands(self, *args, **kwargs):
        path = real_create(self, *args, **kwargs)
        f.write_bytes(b'{"name": "late external write"}')  # after verification 1
        return path

    monkeypatch.setattr(BackupStore, "create_from_bytes", create_then_other_writer_lands)
    with pytest.raises(ProjectConflictError):
        repo.save(project, f, expected_stamp=first.stamp)
    monkeypatch.undo()

    assert f.read_bytes() == b'{"name": "late external write"}'
    assert [n for n in _names(tmp_path) if n.startswith(".voxora_tmp_")] == []


def test_backup_failure_aborts_the_save_unless_explicitly_allowed(tmp_path):
    blocker = tmp_path / "bk"
    blocker.write_text("not a folder")
    repo = JsonProjectRepository(BackupStore(blocker))
    f = tmp_path / "p.voxora"
    project = _project()
    first = JsonProjectRepository().save(project, f)  # plain first save
    original = f.read_bytes()

    project.scenes[0].text = "new"
    with pytest.raises(ProjectBackupError, match="not saved"):
        repo.save(project, f, expected_stamp=first.stamp)
    assert f.read_bytes() == original and _names(tmp_path) == ["bk", "p.voxora"]

    outcome = repo.save(project, f, expected_stamp=first.stamp, allow_without_backup=True)
    assert outcome.backup_path is None and "new" in f.read_text(encoding="utf-8")


def test_permission_retry_delays_are_wired_through_the_repository(tmp_path, monkeypatch):
    delays = []
    repo = JsonProjectRepository(sleep=delays.append)
    original = Path.replace
    calls = []

    def flaky(self, destination):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError("briefly locked")
        return original(self, destination)

    monkeypatch.setattr(Path, "replace", flaky)
    repo.save(_project(), tmp_path / "p.voxora")
    monkeypatch.undo()
    assert delays == [0.05]


# --------------------------------------------------- manager level: two windows


def test_second_manager_saving_the_same_file_gets_a_conflict_and_stays_dirty(tmp_path):
    f = tmp_path / "shared.voxora"
    seed = ProjectManager()
    seed.current_project.scenes.append(Scene(title="S", text="start", order=0))
    seed.save(f)

    a, b = ProjectManager(), ProjectManager()
    a.open(f)
    b.open(f)
    a.current_project.scenes[0].text = "A's edit"
    a.mark_dirty()
    a.save()

    b.current_project.scenes[0].text = "B's edit"
    b.mark_dirty()
    with pytest.raises(ProjectConflictError):
        b.save()

    assert b.dirty is True and b.current_path == f
    assert "A's edit" in f.read_text(encoding="utf-8")  # A's save survived

    other = b.save(tmp_path / "b_copy.voxora")  # Save As is the way out
    assert "B's edit" in other.read_text(encoding="utf-8")
    assert b.dirty is False and b.current_path == other
