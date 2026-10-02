from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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

    # Per-scene TTS settings -- already here since Phase 1/2; Phase 3 just
    # adds the script/scene-management fields around them. Keeping these
    # unused-for-now fields is what lets a future phase associate generated
    # audio with a specific scene without another model migration.
    voice_id: Optional[str] = None
    provider: Optional[str] = None
    speed: float = 1.0
    pitch: Optional[str] = None
    style: Optional[str] = None
    pause_ms: int = 0
    audio_path: Optional[Path] = None

    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()