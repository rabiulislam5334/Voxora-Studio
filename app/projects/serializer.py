from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.core.exceptions import ProjectError
from app.models.project import Project
from app.models.scene import Scene

# Bump this and add a migration path if the on-disk shape ever changes in
# a way old code can't read. Opening a file with a HIGHER version than
# this must fail loudly (see project_from_dict) rather than silently
# dropping fields it doesn't understand.
CURRENT_SCHEMA_VERSION = 1


def _parse_datetime(value: Any) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _with_extra(known: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Append preserved unknown keys after the known ones. A known key is
    never overridden by an ``extra`` entry."""
    for key, value in extra.items():
        if key not in known:
            known[key] = copy.deepcopy(value)
    return known


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
        # Phase 4 fields -- always written for new saves; absent entirely
        # in files saved by Phase 3, which scene_from_dict below handles.
        "pitch_hz": scene.pitch_hz,
        "volume_percent": scene.volume_percent,
        "sentence_pause_ms": scene.sentence_pause_ms,
        "paragraph_pause_ms": scene.paragraph_pause_ms,
        "scene_pause_ms": scene.scene_pause_ms,
        "created_at": scene.created_at.isoformat(),
        "updated_at": scene.updated_at.isoformat(),
    }, scene.extra)


def scene_from_dict(data: Dict[str, Any]) -> Scene:
    if not isinstance(data, dict):
        raise ProjectError("A scene entry in this project file is not a valid object.")

    scene_id = data.get("id")
    if not scene_id:
        raise ProjectError("A scene in this project file is missing its id.")

    audio_path = data.get("audio_path")
    return Scene(
        id=scene_id,
        title=data.get("title") or "Untitled Scene",
        text=data.get("text", ""),
        notes=data.get("notes", ""),
        visual_prompt=data.get("visual_prompt", ""),
        order=data.get("order", 0),
        voice_id=data.get("voice_id"),
        provider=data.get("provider"),
        speed=data.get("speed", 1.0),
        pitch=data.get("pitch"),
        style=data.get("style"),
        pause_ms=data.get("pause_ms", 0),
        audio_path=Path(audio_path) if audio_path else None,
        # Phase 4 fields: .get(..., None) means a Phase-3-era project file
        # (which has none of these keys at all) loads with every one of
        # them defaulting to None -- "use current Voice page settings" --
        # exactly the safe-default, no-crash, no-migration behavior
        # required for backward compatibility.
        pitch_hz=data.get("pitch_hz"),
        volume_percent=data.get("volume_percent"),
        sentence_pause_ms=data.get("sentence_pause_ms"),
        paragraph_pause_ms=data.get("paragraph_pause_ms"),
        scene_pause_ms=data.get("scene_pause_ms"),
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
        extra={k: copy.deepcopy(v) for k, v in data.items() if k not in _SCENE_KEYS},
    )


def project_to_dict(project: Project) -> Dict[str, Any]:
    ordered_scenes = sorted(project.scenes, key=lambda s: s.order)
    return _with_extra({
        "schema_version": project.schema_version,
        "id": project.id,
        "name": project.name,
        "language": project.language,
        "settings": project.settings,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "scenes": [scene_to_dict(s) for s in ordered_scenes],
    }, project.extra)


def project_from_dict(data: Dict[str, Any]) -> Project:
    if not isinstance(data, dict):
        raise ProjectError("Project file does not contain a valid project object.")

    schema_version = data.get("schema_version", 1)
    if not isinstance(schema_version, int):
        raise ProjectError("Project file has an invalid schema_version field.")
    if schema_version > CURRENT_SCHEMA_VERSION:
        raise ProjectError(
            f"This project file was created with a newer version of Voxora Studio "
            f"(schema version {schema_version}, this app supports up to "
            f"{CURRENT_SCHEMA_VERSION}). Please update the application to open it."
        )

    scenes_data = data.get("scenes", [])
    if not isinstance(scenes_data, list):
        raise ProjectError("Project file's 'scenes' field is invalid.")

    scenes = [scene_from_dict(s) for s in scenes_data]

    seen_ids = set()
    for scene in scenes:
        if scene.id in seen_ids:
            raise ProjectError(f"Project file contains a duplicate scene id: {scene.id}")
        seen_ids.add(scene.id)

    scenes.sort(key=lambda s: s.order)

    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}

    return Project(
        id=data.get("id") or uuid.uuid4().hex[:12],
        name=data.get("name") or "Untitled Project",
        language=data.get("language", "en"),
        settings=settings,
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
        scenes=scenes,
        schema_version=schema_version,
        extra={k: copy.deepcopy(v) for k, v in data.items() if k not in _PROJECT_KEYS},
    )


# The keys this version writes, derived from the writers above so the two can
# never drift apart. Anything else found in a file is preserved as ``extra``.
_SCENE_KEYS = frozenset(scene_to_dict(Scene()))
_PROJECT_KEYS = frozenset(project_to_dict(Project()))