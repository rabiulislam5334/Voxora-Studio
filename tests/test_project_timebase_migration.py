from __future__ import annotations

import copy

import pytest

from app.core.exceptions import ProjectError
from app.core.timebase import TICKS_PER_SECOND
from app.models.project import Project
from app.projects.serializer import CURRENT_SCHEMA_VERSION, project_from_dict, project_to_dict


def test_new_project_declares_canonical_timebase():
    data = project_to_dict(Project())
    assert CURRENT_SCHEMA_VERSION == 4
    assert data["schema_version"] == 4
    assert data["timebase"] == {
        "format_version": 1,
        "ticks_per_second": TICKS_PER_SECOND,
    }


def test_schema_v3_migration_adds_timebase_without_rewriting_legacy_settings():
    raw = {
        "schema_version": 3,
        "settings": {
            "theme": "dark",
            "studio": {
                "audio": {"tracks": [{"path": "music.mp3", "offset_s": 1.25}]},
                "video": {"transition_s": 0.5},
            },
        },
        "subtitles": {"format_version": 1, "tracks": []},
        "scenes": [{"id": "scene-1", "order": 0}],
    }
    original = copy.deepcopy(raw)

    project = project_from_dict(raw)
    saved = project_to_dict(project)

    assert raw == original
    assert project.schema_version == 4
    assert saved["schema_version"] == 4
    assert saved["timebase"]["ticks_per_second"] == TICKS_PER_SECOND
    assert saved["settings"] == original["settings"]
    assert saved["subtitles"] == original["subtitles"]


@pytest.mark.parametrize(
    "timebase",
    [
        [],
        {"format_version": True, "ticks_per_second": TICKS_PER_SECOND},
        {"format_version": 2, "ticks_per_second": TICKS_PER_SECOND},
        {"format_version": 1, "ticks_per_second": True},
        {"format_version": 1, "ticks_per_second": 1},
    ],
)
def test_invalid_or_unsupported_project_timebase_is_rejected(timebase):
    with pytest.raises(ProjectError, match="timebase"):
        project_from_dict({
            "schema_version": 4,
            "timebase": timebase,
            "scenes": [],
        })


def test_missing_timebase_in_v4_file_uses_canonical_default():
    project = project_from_dict({"schema_version": 4, "scenes": []})
    assert project.timebase["ticks_per_second"] == TICKS_PER_SECOND
