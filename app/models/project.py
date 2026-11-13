from __future__ import annotations

import uuid
from dataclasses import InitVar, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.models.scene import Scene


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Project:
    id: str = field(default_factory=_new_id)
    name: str = "Untitled Project"
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    language: str = "en"
    scenes: List[Scene] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    schema_version: int = 2
    # Additive v2 containers. Their inner schemas remain intentionally
    # unopinionated until the owning engines define them.
    profile: Dict[str, Any] = field(default_factory=dict)
    assets: Dict[str, Any] = field(default_factory=dict)
    director: Dict[str, Any] = field(default_factory=dict)
    migration: Dict[str, Any] = field(default_factory=dict)
    # Canonical v2 name; InitVar accepts the historical constructor keyword.
    extras: Dict[str, Any] = field(default_factory=dict)
    extra: InitVar[Optional[Dict[str, Any]]] = None

    def touch(self) -> None:
        self.updated_at = _utcnow()

    def add_scene(self, scene: Optional[Scene] = None) -> Scene:
        if scene is None:
            scene = Scene(title=f"Scene {len(self.scenes) + 1}")
        scene.order = len(self.scenes)
        self.scenes.append(scene)
        self.touch()
        return scene

    def get_scene(self, scene_id: str) -> Optional[Scene]:
        return next((s for s in self.scenes if s.id == scene_id), None)

    def rename_scene(self, scene_id: str, new_title: str) -> None:
        scene = self._require_scene(scene_id)
        scene.title = new_title
        scene.touch()
        self.touch()

    def duplicate_scene(self, scene_id: str) -> Scene:
        original = self._require_scene(scene_id)
        copy_scene = Scene(
            title=f"{original.title} (Copy)",
            text=original.text,
            notes=original.notes,
            visual_prompt=original.visual_prompt,
            voice_id=original.voice_id,
            provider=original.provider,
            speed=original.speed,
            pitch=original.pitch,
            style=original.style,
            pause_ms=original.pause_ms,
            pitch_hz=original.pitch_hz,
            volume_percent=original.volume_percent,
            sentence_pause_ms=original.sentence_pause_ms,
            paragraph_pause_ms=original.paragraph_pause_ms,
            scene_pause_ms=original.scene_pause_ms,
        )
        index = self.scenes.index(original)
        self.scenes.insert(index + 1, copy_scene)
        self._renumber()
        self.touch()
        return copy_scene

    def delete_scene(self, scene_id: str) -> None:
        scene = self._require_scene(scene_id)
        self.scenes.remove(scene)
        self._renumber()
        self.touch()

    def move_scene_up(self, scene_id: str) -> None:
        index = self._index_of(scene_id)
        if index > 0:
            self.scenes[index - 1], self.scenes[index] = self.scenes[index], self.scenes[index - 1]
            self._renumber()
            self.touch()

    def move_scene_down(self, scene_id: str) -> None:
        index = self._index_of(scene_id)
        if 0 <= index < len(self.scenes) - 1:
            self.scenes[index + 1], self.scenes[index] = self.scenes[index], self.scenes[index + 1]
            self._renumber()
            self.touch()

    def total_word_count(self) -> int:
        from app.text.wordcount import count_words
        return sum(count_words(s.text) for s in self.scenes)

    def _require_scene(self, scene_id: str) -> Scene:
        scene = self.get_scene(scene_id)
        if scene is None:
            raise ValueError(f"No scene with id '{scene_id}' in this project.")
        return scene

    def _index_of(self, scene_id: str) -> int:
        for i, scene in enumerate(self.scenes):
            if scene.id == scene_id:
                return i
        return -1

    def _renumber(self) -> None:
        for i, scene in enumerate(self.scenes):
            scene.order = i


# Backwards-compatible attribute alias; the dataclass field is now "extras".
def _get_extra(self):
    return self.extras

def _set_extra(self, value):
    if value is not None:
        self.extras = value

Project.extra = property(_get_extra, _set_extra)
