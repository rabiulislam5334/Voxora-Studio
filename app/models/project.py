from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

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

    def touch(self) -> None:
        self.updated_at = _utcnow()

    def add_scene(self, scene: Scene) -> None:
        self.scenes.append(scene)
        self.touch()