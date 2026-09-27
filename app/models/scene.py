from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Scene:
    id: str = field(default_factory=_new_id)
    title: str = "Untitled Scene"
    text: str = ""
    voice_id: Optional[str] = None
    provider: Optional[str] = None
    speed: float = 1.0
    pitch: Optional[str] = None
    style: Optional[str] = None
    pause_ms: int = 0
    audio_path: Optional[Path] = None