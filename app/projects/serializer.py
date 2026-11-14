from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.core.exceptions import ProjectError
from app.models.project import Project
from app.models.scene import Scene
from app.core.timebase import TICKS_PER_SECOND

CURRENT_SCHEMA_VERSION = 4
V1_SCHEMA_VERSION = 1
SUBTITLES_FORMAT_VERSION = 1
TIMEBASE_FORMAT_VERSION = 1


def _parse_datetime(value: Any) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _with_extra(known: Dict[str, Any], extras: Dict[str, Any]) -> Dict[str, Any]:
    """Append preserved unknown keys; unknown data never overrides known keys."""
    for key, value in extras.items():
        if key not in known:
            known[key] = copy.deepcopy(value)
    return known


def _schema_version(data: Dict[str, Any]) -> int:
    version = data.get("schema_version", V1_SCHEMA_VERSION)
    # bool is a subclass of int in Python; it is not a valid schema version.
    if type(version) is not int or version < 1:
        raise ProjectError("Project file has an invalid schema_version field.")
    if version > CURRENT_SCHEMA_VERSION:
        raise ProjectError(
            f"This project file was created with a newer version of Voxora Studio "
            f"(schema version {version}, this app supports up to {CURRENT_SCHEMA_VERSION}). "
            "Please update the application to open it."
        )
    return version


def _empty_subtitles_data() -> Dict[str, Any]:
    return {"format_version": SUBTITLES_FORMAT_VERSION, "tracks": []}


def _empty_timebase_data() -> Dict[str, Any]:
    return {"format_version": TIMEBASE_FORMAT_VERSION, "ticks_per_second": TICKS_PER_SECOND}


def _validate_timebase(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ProjectError("Project file's 'timebase' field must be an object.")
    version = data.get("format_version", TIMEBASE_FORMAT_VERSION)
    if type(version) is not int or version < 1:
        raise ProjectError("Project file's 'timebase.format_version' must be a positive integer.")
    if version > TIMEBASE_FORMAT_VERSION:
        raise ProjectError("This project uses a newer timebase data format. Please update Voxora Studio.")
    ticks_per_second = data.get("ticks_per_second", TICKS_PER_SECOND)
    if type(ticks_per_second) is not int or ticks_per_second != TICKS_PER_SECOND:
        raise ProjectError(
            "Project file uses an unsupported canonical timebase; expected "
            f"{TICKS_PER_SECOND} ticks per second."
        )
    result = copy.deepcopy(data)
    result.setdefault("format_version", TIMEBASE_FORMAT_VERSION)
    result.setdefault("ticks_per_second", TICKS_PER_SECOND)
    return result


def _migrate_project_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return an additive v3 copy. Never mutate the caller's parsed JSON."""
    version = _schema_version(data)
    migrated = copy.deepcopy(data)

    if version == 1:
        migrated.setdefault("profile", {})
        migrated.setdefault("assets", {})
        migrated.setdefault("director", {})
        migrated["migration"] = {"from_schema_version": 1}
        migrated["schema_version"] = 2
        version = 2

    for key in ("profile", "assets", "director", "migration"):
        if key not in migrated:
            migrated[key] = {}
        if not isinstance(migrated[key], dict):
            raise ProjectError(f"Project file's '{key}' field must be an object.")

    if version == 2:
        # v3 adds a separate project-level namespace. Existing settings.studio
        # is intentionally left untouched.
        migrated.setdefault("subtitles", _empty_subtitles_data())
        migrated["schema_version"] = 3
        version = 3

    if version == 3:
        # v4 declares the canonical project clock without rewriting legacy
        # seconds-based settings or subtitle payloads.
        migrated.setdefault("timebase", _empty_timebase_data())
        migrated["schema_version"] = 4

    subtitles = migrated.get("subtitles", _empty_subtitles_data())
    if not isinstance(subtitles, dict):
        raise ProjectError("Project file's 'subtitles' field must be an object.")
    format_version = subtitles.get("format_version", SUBTITLES_FORMAT_VERSION)
    if type(format_version) is not int or format_version < 1:
        raise ProjectError("Project file's 'subtitles.format_version' must be a positive integer.")
    if format_version > SUBTITLES_FORMAT_VERSION:
        raise ProjectError(
            "This project uses a newer subtitle data format. Please update Voxora Studio."
        )
    tracks = subtitles.get("tracks", [])
    if not isinstance(tracks, list):
        raise ProjectError("Project file's 'subtitles.tracks' field must be a list.")
    subtitles.setdefault("format_version", SUBTITLES_FORMAT_VERSION)
    subtitles.setdefault("tracks", [])
    migrated["subtitles"] = subtitles
    migrated["timebase"] = _validate_timebase(migrated.get("timebase", _empty_timebase_data()))
    return migrated


def scene_to_dict(scene: Scene) -> Dict[str, Any]:
    return _with_extra({
        "id": scene.id,
        "title": scene.title,
        "text": scene.text,
        "notes": scene.notes,
        "visual_prompt": scene.visual_prompt,
        "order": scene.order,
        "voice_id": scene.voice_id,
        "provider": scene.provider,
        "speed": scene.speed,
        "pitch": scene.pitch,
        "style": scene.style,
        "pause_ms": scene.pause_ms,
        "audio_path": str(scene.audio_path) if scene.audio_path else None,
        "pitch_hz": scene.pitch_hz,
        "volume_percent": scene.volume_percent,
        "sentence_pause_ms": scene.sentence_pause_ms,
        "paragraph_pause_ms": scene.paragraph_pause_ms,
        "scene_pause_ms": scene.scene_pause_ms,
        "created_at": scene.created_at.isoformat(),
        "updated_at": scene.updated_at.isoformat(),
    }, scene.extras)


def scene_from_dict(data: Dict[str, Any]) -> Scene:
    if not isinstance(data, dict):
        raise ProjectError("A scene entry in this project file is not a valid object.")
    scene_id = data.get("id")
    if not scene_id:
        raise ProjectError("A scene in this project file is missing its id.")

    order = data.get("order", 0)
    if type(order) is not int:
        raise ProjectError("A scene's 'order' must be an integer (booleans are not accepted).")

    text_value = data.get("text", "")
    if text_value is None:
        text_value = ""
    if not isinstance(text_value, str):
        raise ProjectError("A scene's 'text' field must be a string or null.")

    audio_path = data.get("audio_path")
    return Scene(
        id=scene_id,
        title=data.get("title") or "Untitled Scene",
        text=text_value,
        notes=data.get("notes", ""),
        visual_prompt=data.get("visual_prompt", ""),
        order=order,
        voice_id=data.get("voice_id"),
        provider=data.get("provider"),
        speed=data.get("speed", 1.0),
        pitch=data.get("pitch"),
        style=data.get("style"),
        pause_ms=data.get("pause_ms", 0),
        audio_path=Path(audio_path) if audio_path else None,
        pitch_hz=data.get("pitch_hz"),
        volume_percent=data.get("volume_percent"),
        sentence_pause_ms=data.get("sentence_pause_ms"),
        paragraph_pause_ms=data.get("paragraph_pause_ms"),
        scene_pause_ms=data.get("scene_pause_ms"),
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
        extras={k: copy.deepcopy(v) for k, v in data.items() if k not in _SCENE_KEYS},
    )


def project_to_dict(project: Project) -> Dict[str, Any]:
    ordered_scenes = sorted(project.scenes, key=lambda s: s.order)
    return _with_extra({
        "schema_version": CURRENT_SCHEMA_VERSION,
        "id": project.id,
        "name": project.name,
        "language": project.language,
        "settings": copy.deepcopy(project.settings),
        "profile": copy.deepcopy(project.profile),
        "assets": copy.deepcopy(project.assets),
        "director": copy.deepcopy(project.director),
        "migration": copy.deepcopy(project.migration),
        "subtitles": copy.deepcopy(project.subtitles),
        "timebase": copy.deepcopy(project.timebase),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "scenes": [scene_to_dict(s) for s in ordered_scenes],
    }, project.extras)


def project_from_dict(data: Dict[str, Any]) -> Project:
    if not isinstance(data, dict):
        raise ProjectError("Project file does not contain a valid project object.")

    migrated = _migrate_project_data(data)
    scenes_data = migrated.get("scenes", [])
    if not isinstance(scenes_data, list):
        raise ProjectError("Project file's 'scenes' field is invalid.")
    scenes = [scene_from_dict(scene) for scene in scenes_data]

    seen_ids = set()
    for scene in scenes:
        if scene.id in seen_ids:
            raise ProjectError(f"Project file contains a duplicate scene id: {scene.id}")
        seen_ids.add(scene.id)
    scenes.sort(key=lambda scene: scene.order)

    settings = migrated.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}

    return Project(
        id=migrated.get("id") or uuid.uuid4().hex[:12],
        name=migrated.get("name") or "Untitled Project",
        language=migrated.get("language", "en"),
        settings=settings,
        created_at=_parse_datetime(migrated.get("created_at")),
        updated_at=_parse_datetime(migrated.get("updated_at")),
        scenes=scenes,
        schema_version=CURRENT_SCHEMA_VERSION,
        profile=copy.deepcopy(migrated["profile"]),
        assets=copy.deepcopy(migrated["assets"]),
        director=copy.deepcopy(migrated["director"]),
        migration=copy.deepcopy(migrated["migration"]),
        subtitles=copy.deepcopy(migrated["subtitles"]),
        timebase=copy.deepcopy(migrated["timebase"]),
        extras={k: copy.deepcopy(v) for k, v in migrated.items() if k not in _PROJECT_KEYS},
    )


_SCENE_KEYS = frozenset(scene_to_dict(Scene()))
_PROJECT_KEYS = frozenset(project_to_dict(Project()))
