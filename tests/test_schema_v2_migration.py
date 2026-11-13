from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.exceptions import ProjectBackupError, ProjectError
from app.models.project import Project
from app.projects.manager import ProjectManager
from app.projects.serializer import CURRENT_SCHEMA_VERSION, project_from_dict, project_to_dict

FIXTURES = Path(__file__).parent / "fixtures" / "v1"


def test_v1_load_is_in_memory_only_and_first_save_creates_exact_backup(tmp_path):
    source = tmp_path / "episode.voxora"
    original = (FIXTURES / "v1_full.voxora").read_bytes()
    source.write_bytes(original)

    manager = ProjectManager()
    manager.open(source)
    assert manager.current_project.schema_version == 3
    assert source.read_bytes() == original

    manager.current_project.name = "Migrated"
    manager.mark_dirty()
    manager.save()

    backup = tmp_path / "episode.v1-backup"
    assert backup.read_bytes() == original
    saved = json.loads(source.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 3
    assert saved["subtitles"] == {"format_version": 1, "tracks": []}
    assert saved["settings"]["studio"] == json.loads(original)["settings"]["studio"]


def test_v1_backup_is_created_once_and_never_overwritten(tmp_path):
    source = tmp_path / "episode.voxora"
    original = (FIXTURES / "v1_minimal.voxora").read_bytes()
    source.write_bytes(original)
    manager = ProjectManager()
    manager.open(source)
    manager.current_project.name = "First edit"
    manager.mark_dirty()
    manager.save()

    backup = tmp_path / "episode.v1-backup"
    assert backup.read_bytes() == original
    backup.write_bytes(b"preserve this existing backup")

    manager.current_project.name = "Second edit"
    manager.mark_dirty()
    manager.save()
    assert backup.read_bytes() == b"preserve this existing backup"


def test_v1_backup_failure_aborts_save_and_keeps_original_and_dirty_state(tmp_path, monkeypatch):
    source = tmp_path / "episode.voxora"
    original = (FIXTURES / "v1_minimal.voxora").read_bytes()
    source.write_bytes(original)
    manager = ProjectManager()
    manager.open(source)
    manager.current_project.name = "Unsaved change"
    manager.mark_dirty()

    def fail_link(*args, **kwargs):
        raise OSError("simulated backup failure")

    monkeypatch.setattr("app.persistence.repository.os.link", fail_link)
    with pytest.raises(ProjectBackupError, match="one-time v1 backup"):
        manager.save()

    assert source.read_bytes() == original
    assert manager.dirty is True
    assert not (tmp_path / "episode.v1-backup").exists()


def test_v1_migration_is_idempotent_and_preserves_unknown_keys():
    raw = json.loads((FIXTURES / "v1_unknown_keys.voxora").read_text(encoding="utf-8"))
    once = project_to_dict(project_from_dict(raw))
    twice = project_to_dict(project_from_dict(once))
    assert once == twice
    assert once["schema_version"] == CURRENT_SCHEMA_VERSION
    assert once["future_top_level_key"] == {"hello": "world"}
    assert once["scenes"][0]["future_scene_key"] == 42


def test_schema_v2_containers_and_studio_settings_roundtrip():
    raw = {
        "schema_version": 2,
        "id": "v2project001",
        "settings": {"studio": {"audio": {"tracks": []}, "custom": {"keep": True}}},
        "profile": {"id": "quasivanta", "overrides": {"visual_style": "cinematic"}},
        "assets": {"items": [{"id": "asset-1", "path": "media/ocean.jpg"}]},
        "director": {"mode": "manual", "cycle": ["wide", "close"]},
        "migration": {"from_schema_version": 1},
        "scenes": [{"id": "scene-1", "order": 0, "text": "Hello"}],
    }
    out = project_to_dict(project_from_dict(raw))
    assert out["schema_version"] == 3
    assert out["subtitles"] == {"format_version": 1, "tracks": []}
    assert out["profile"] == raw["profile"]
    assert out["assets"] == raw["assets"]
    assert out["director"] == raw["director"]
    assert out["migration"] == raw["migration"]
    assert out["settings"]["studio"] == raw["settings"]["studio"]
    assert out["scenes"][0]["id"] == "scene-1"
    assert out["scenes"][0]["order"] == 0
    assert out["scenes"][0]["text"] == "Hello"


@pytest.mark.parametrize("order", [True, False, "1", 1.0, None])
def test_invalid_scene_order_values_raise_project_error(order):
    with pytest.raises(ProjectError, match="order.*integer"):
        project_from_dict({"scenes": [{"id": "scene-1", "order": order}]})


def test_null_scene_text_is_normalized_to_empty_string():
    project = project_from_dict({"scenes": [{"id": "scene-1", "text": None}]})
    assert project.scenes[0].text == ""


@pytest.mark.parametrize("key", ["profile", "assets", "director", "migration"])
def test_invalid_v2_container_shape_is_rejected(key):
    with pytest.raises(ProjectError, match=key):
        project_from_dict({"schema_version": 2, key: []})


def test_v2_project_preserves_unrecognized_top_level_and_scene_data():
    raw = {
        "schema_version": 2,
        "profile": {},
        "assets": {},
        "director": {},
        "migration": {},
        "future_project_data": {"a": [1, 2]},
        "scenes": [{"id": "scene-1", "future_scene_data": {"keep": "yes"}}],
    }
    project = project_from_dict(raw)
    assert project.extras == {"future_project_data": {"a": [1, 2]}}
    assert project.scenes[0].extras == {"future_scene_data": {"keep": "yes"}}
    assert project_to_dict(project)["future_project_data"] == {"a": [1, 2]}



def test_extras_is_the_canonical_model_field_with_legacy_extra_alias():
    from app.models.scene import Scene

    project = Project(extras={"future": 1})
    scene = Scene(extras={"future_scene": 2})
    assert project.extras == {"future": 1}
    assert project.extra == project.extras
    assert scene.extras == {"future_scene": 2}
    assert scene.extra == scene.extras

    legacy_project = Project(extra={"legacy": True})
    legacy_scene = Scene(extra={"legacy_scene": True})
    assert legacy_project.extras == {"legacy": True}
    assert legacy_scene.extras == {"legacy_scene": True}



def test_v1_backup_path_that_is_a_directory_aborts_without_touching_project(tmp_path):
    source = tmp_path / "episode.voxora"
    original = (FIXTURES / "v1_minimal.voxora").read_bytes()
    source.write_bytes(original)
    (tmp_path / "episode.v1-backup").mkdir()

    manager = ProjectManager()
    manager.open(source)
    manager.current_project.name = "Edited"
    manager.mark_dirty()

    with pytest.raises(ProjectBackupError, match="not a file"):
        manager.save()
    assert source.read_bytes() == original
    assert manager.dirty is True
