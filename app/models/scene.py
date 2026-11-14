from __future__ import annotations

import uuid
from dataclasses import InitVar, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Scene:
    id: str = field(default_factory=_new_id)
    title: str = "Untitled Scene"
    text: str = ""
    notes: str = ""
    visual_prompt: str = ""
    order: int = 0

    voice_id: Optional[str] = None
    provider: Optional[str] = None
    speed: float = 1.0
    pitch: Optional[str] = None
    style: Optional[str] = None
    pause_ms: int = 0
    audio_path: Optional[Path] = None

    pitch_hz: Optional[int] = None
    volume_percent: Optional[int] = None
    sentence_pause_ms: Optional[int] = None
    paragraph_pause_ms: Optional[int] = None
    scene_pause_ms: Optional[int] = None

    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    # Canonical v2 name; InitVar accepts the historical constructor keyword.
    extras: Dict[str, Any] = field(default_factory=dict)
    extra: InitVar[Optional[Dict[str, Any]]] = None

    def __post_init__(self, extra: Optional[Dict[str, Any]]) -> None:
        if extra is not None:
            self.extras = extra

    def touch(self) -> None:
        self.updated_at = _utcnow()


# Backwards-compatible attribute alias; the dataclass field is now "extras".
def _get_extra(self):
    return self.extras

def _set_extra(self, value):
    if value is not None:
        self.extras = value

Scene.extra = property(_get_extra, _set_extra)
