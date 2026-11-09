"""Step 2 -- revision counter, save-state tracking, dirty preservation."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import ProjectConflictError, ProjectError
from app.models.project import Project
from app.persistence.repository import SaveOutcome
from app.persistence.stamps import stamp_from_bytes
from app.projects.manager import ProjectManager


def test_revisions_only_increase_across_edits_and_across_managers():
    first, second = ProjectManager(), ProjectManager()
    seen = [first.revision, second.revision]
    for _ in range(3):
        first.mark_dirty()
        seen.append(first.revision)
    second.new_project()
    seen.append(second.revision)

    assert seen == sorted(seen) and len(set(seen)) == len(seen)


def test_new_and_open_start_clean_at_a_fresh_revision(tmp_path):
    m = ProjectManager()
    before = m.revision
    m.new_project("X")
    assert m.revision > before and m.saved_revision == m.revision and not m.dirty

    f = m.save(tmp_path / "x.voxora")
    other = ProjectManager()
    other.open(f)
    assert other.saved_revision == other.revision and not other.dirty
    assert other.last_save is None


def test_save_records_the_revision_that_was_written(tmp_path):
    m = ProjectManager()
    m.mark_dirty()
    revision = m.revision
    path = m.save(tmp_path / "p.voxora")

    assert m.saved_revision == revision and m.dirty is False
    assert m.last_save.revision == revision and m.last_save.path == path
    assert m.last_save.stamp.sha256 == stamp_from_bytes(path.read_bytes()).sha256


def test_failed_save_preserves_dirty_state_and_revisions(tmp_path, monkeypatch):
    m = ProjectManager()
    target = m.save(tmp_path / "p.voxora")
    m.mark_dirty()
    revision, saved, last = m.revision, m.saved_revision, m.last_save

    def boom(self, *args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", boom)
    with pytest.raises(ProjectError):
        m.save()
    monkeypatch.undo()

    assert m.dirty is True and m.revision == revision and m.saved_revision == saved
    assert m.last_save is last and m.current_path == target


def test_conflict_also_preserves_dirty_state(tmp_path):
    m = ProjectManager()
    target = m.save(tmp_path / "p.voxora")
    target.write_bytes(b'{"name": "someone else"}')
    m.mark_dirty()
    revision, saved = m.revision, m.saved_revision

    with pytest.raises(ProjectConflictError):
        m.save()
    assert m.dirty is True and m.revision == revision and m.saved_revision == saved


def test_an_edit_during_save_keeps_the_project_dirty():
    class MutatingRepo:
        manager = None

        def serialize(self, project):
            return b"{}"

        def load(self, path):
            raise AssertionError

        def save(self, project, path, *, expected_stamp=None, allow_without_backup=False):
            self.manager.mark_dirty()  # an edit lands while the save runs
            return SaveOutcome(path=path, stamp=stamp_from_bytes(b"{}"), backup_path=None)

    repo = MutatingRepo()
    m = ProjectManager(repo)
    repo.manager = m
    m.mark_dirty()
    revision_at_save = m.revision
    m.save(Path("x.voxora"))

    assert m.saved_revision == revision_at_save
    assert m.revision > m.saved_revision and m.dirty is True


def test_dirty_with_a_stale_revision_is_repaired_by_the_failsafe():
    m = ProjectManager()
    m.dirty = True  # set without going through mark_dirty()
    assert m.revision <= m.saved_revision
    assert m.ensure_dirty_revision() is True
    assert m.revision > m.saved_revision
    assert m.ensure_dirty_revision() is False  # idempotent


def test_serialize_snapshot_pairs_bytes_with_the_revision_and_changes_nothing():
    m = ProjectManager()
    m.mark_dirty()
    updated = m.current_project.updated_at
    data, revision = m.serialize_snapshot()

    assert revision == m.revision and m.dirty is True
    assert m.current_project.updated_at == updated
    assert b'"schema_version"' in data


def test_adopt_dirty_counts_as_newer_than_saved_and_is_unbound():
    m = ProjectManager()
    m.adopt(Project(name="Recovered"), path=None, dirty=True)
    assert m.dirty and m.current_path is None
    assert m.revision > m.saved_revision
    assert m.current_project.name == "Recovered"

    m.adopt(Project(name="Clean"), path=None, dirty=False)
    assert not m.dirty and m.revision == m.saved_revision
