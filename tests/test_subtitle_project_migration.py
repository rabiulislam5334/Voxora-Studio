from __future__ import annotations

import copy

import pytest

from app.core.exceptions import ProjectError
from app.models.project import Project
from app.projects.serializer import (
    CURRENT_SCHEMA_VERSION,
    project_from_dict,
    project_to_dict,
)


def _project_data(schema_version: int) -> dict:
    return {
        "schema_version": schema_version,
        "id": "project-1",
        "name": "Subtitle migration fixture",
        "language": "en",
        "settings": {"studio": {"audio": {"narration_volume_percent": 85}}},
        "scenes": [],
    }


def test_new_project_serializes_with_v3_empty_subtitle_namespace():
    data = project_to_dict(Project())

    assert CURRENT_SCHEMA_VERSION == 3
    assert data["schema_version"] == 3
    assert data["subtitles"] == {"format_version": 1, "tracks": []}


@pytest.mark.parametrize("source_version", [1, 2])
def test_v1_and_v2_projects_migrate_additively_to_v3(source_version: int):
    original = _project_data(source_version)
    original_copy = copy.deepcopy(original)

    project = project_from_dict(original)
    serialized = project_to_dict(project)

    assert original == original_copy  # migration never mutates parsed source data
    assert project.schema_version == 3
    assert serialized["schema_version"] == 3
    assert serialized["subtitles"] == {"format_version": 1, "tracks": []}
    assert project.settings == original["settings"]
    if source_version == 1:
        assert project.migration == {"from_schema_version": 1}
    else:
        assert project.migration == {}


def test_v3_subtitle_payload_round_trips_without_mutation_or_loss():
    subtitle_payload = {
        "format_version": 1,
        "tracks": [{"id": "track-en", "language": "en", "captions": []}],
        "future_extension": {"keep": True},
    }
    data = _project_data(3)
    data["subtitles"] = copy.deepcopy(subtitle_payload)

    project = project_from_dict(data)
    serialized = project_to_dict(project)

    assert project.subtitles == subtitle_payload
    assert serialized["subtitles"] == subtitle_payload
    assert data["subtitles"] == subtitle_payload


@pytest.mark.parametrize(
    ("subtitle_payload", "message"),
    [
        ([], "subtitles.*object"),
        ({"format_version": True, "tracks": []}, "format_version"),
        ({"format_version": 2, "tracks": []}, "newer subtitle data format"),
        ({"format_version": 1, "tracks": {}}, "tracks.*list"),
    ],
)
def test_invalid_or_unsupported_subtitle_container_fails_loudly(
    subtitle_payload, message: str
):
    data = _project_data(3)
    data["subtitles"] = subtitle_payload

    with pytest.raises(ProjectError, match=message):
        project_from_dict(data)


def test_existing_v2_studio_settings_are_not_moved_or_rewritten():
    data = _project_data(2)
    studio_settings = copy.deepcopy(data["settings"]["studio"])

    project = project_from_dict(data)

    assert project.settings["studio"] == studio_settings
    assert project.subtitles == {"format_version": 1, "tracks": []}
