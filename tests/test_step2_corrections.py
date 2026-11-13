"""Step 2 review corrections: default backups, deleted-file conflict, unknown keys."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import app.core.config as config_module
from app.core.config import AppConfig
from app.core.exceptions import ProjectConflictError
from app.models.project import Project
from app.models.scene import Scene
from app.persistence.backups import BackupStore
from app.persistence.repository import JsonProjectRepository
from app.projects.manager import ProjectManager
from app.projects.serializer import project_from_dict, project_to_dict

FIXTURE = Path(__file__).parent / "fixtures" / "v1" / "v1_unknown_keys.voxora"


def _names(folder: Path):
    return sorted(p.name for p in folder.iterdir())


# ------------------------------------------------ 1. default backups wiring


def test_default_manager_save_creates_a_backup_under_config_backups_dir(tmp_path, monkeypatch):
    config = AppConfig(root_dir=tmp_path / "root")
    monkeypatch.setattr(config_module, "_config", config)

    manager = ProjectManager()  # default construction, as the application does it
    manager.current_project.scenes.append(Scene(title="S", text="one", order=0))
    target = tmp_path / "docs" / "episode.voxora"

    manager.save(target)
    assert manager.last_save.backup_path is None  # first save: nothing to back up
    first_bytes = target.read_bytes()

    manager.current_project.scenes[0].text = "two"
    manager.mark_dirty()
    manager.save()

    backup = manager.last_save.backup_path
    assert backup is not None
    assert backup.parent == config.backups_dir / manager.current_project.id
    assert backup.read_bytes() == first_bytes  # the version that was overwritten
    assert [b.path for b in BackupStore(config.backups_dir).list(manager.current_project.id)] == [backup]
    assert _names(target.parent) == ["episode.voxora"]  # backups never land next to the project


# ------------------------------------------ 2. externally deleted file


def test_repository_raises_conflict_when_the_opened_file_was_deleted(tmp_path):
    repo = JsonProjectRepository()
    f = tmp_path / "p.voxora"
    project = Project(name="P")
    first = repo.save(project, f)

    f.unlink()
    with pytest.raises(ProjectConflictError, match="deleted or moved"):
        repo.save(project, f, expected_stamp=first.stamp)

    assert not f.exists()  # not silently recreated
    assert _names(tmp_path) == []  # and no temp file left behind


def test_repository_without_expected_stamp_still_creates_a_missing_file(tmp_path):
    f = tmp_path / "new.voxora"
    JsonProjectRepository().save(Project(name="P"), f)
    assert f.exists()


def test_manager_keeps_dirty_state_when_file_was_deleted_and_save_as_recovers(tmp_path):
    f = tmp_path / "p.voxora"
    manager = ProjectManager()
    manager.save(f)
    reopened = ProjectManager()
    reopened.open(f)
    reopened.current_project.name = "Edited"
    reopened.mark_dirty()

    f.unlink()
    with pytest.raises(ProjectConflictError):
        reopened.save()

    assert not f.exists()
    assert reopened.dirty is True and reopened.current_path == f

    copy = reopened.save(tmp_path / "recovered.voxora")  # Save As is the way out
    assert json.loads(copy.read_text(encoding="utf-8"))["name"] == "Edited"
    assert reopened.dirty is False and reopened.current_path == copy


# -------------------------------------------------- 3. unknown keys kept


def test_unknown_top_level_and_scene_keys_survive_load_and_dump():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    project = project_from_dict(raw)

    assert project.extra == {"future_top_level_key": {"hello": "world"}}
    assert project.scenes[0].extra == {"future_scene_key": 42}

    out = project_to_dict(project)
    assert out["future_top_level_key"] == {"hello": "world"}
    assert out["scenes"][0]["future_scene_key"] == 42
    assert out["schema_version"] == 3
    assert out["subtitles"] == {"format_version": 1, "tracks": []}
    assert out["profile"] == out["assets"] == out["director"] == {}
    assert out["migration"] == {"from_schema_version": 1}
    for key, value in raw.items():
        if key != "schema_version":
            assert out[key] == value


def test_unknown_keys_survive_open_edit_save_through_the_manager(tmp_path):
    f = tmp_path / "unk.voxora"
    shutil.copyfile(FIXTURE, f)

    manager = ProjectManager()
    manager.open(f)
    manager.current_project.scenes[0].text = "Changed."
    manager.mark_dirty()
    manager.save()

    saved = json.loads(f.read_text(encoding="utf-8"))
    assert saved["scenes"][0]["text"] == "Changed."
    assert saved["future_top_level_key"] == {"hello": "world"}
    assert saved["scenes"][0]["future_scene_key"] == 42


def test_extra_never_overrides_known_keys_and_is_not_shared_with_the_dump():
    project = Project(name="Real", extra={"name": "Fake", "nested": {"a": [1]}})
    out = project_to_dict(project)
    assert out["name"] == "Real"

    out["nested"]["a"].append(2)  # mutating the dump must not touch the model
    assert project.extra["nested"] == {"a": [1]}


def test_files_without_unknown_keys_get_empty_extra():
    project = project_from_dict({"scenes": [{"id": "a"}]})
    assert project.extra == {} and project.scenes[0].extra == {}
