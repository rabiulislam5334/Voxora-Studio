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

    # Phase 4: optional per-scene narration-settings overrides. All
    # default to None, meaning "use the Voice page's current settings" --
    # existing Phase 3 project files have none of these keys and load
    # exactly as before (see app/projects/serializer.py). Not yet read by
    # any UI; Phase 5's scene-by-scene long-form synthesis is the natural
    # future consumer. pitch_hz/volume_percent are the Phase 4 int-based
    # equivalents of the older unused `pitch` string field above, kept
    # separate rather than repurposing that field.
    pitch_hz: Optional[int] = None
    volume_percent: Optional[int] = None
    sentence_pause_ms: Optional[int] = None
    paragraph_pause_ms: Optional[int] = None
    scene_pause_ms: Optional[int] = None

    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def touch(self) -> None:
        self.updated_at = _utcnow()