from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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

    # Kept under the historical field name for source compatibility.
    # The schema/API name is "extras"; the property below exposes that name.
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def extras(self) -> Dict[str, Any]:
        return self.extra

    @extras.setter
    def extras(self, value: Dict[str, Any]) -> None:
        self.extra = value

    def touch(self) -> None:
        self.updated_at = _utcnow()
