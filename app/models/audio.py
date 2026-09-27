from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AudioInfo:
    path: Path
    duration_seconds: Optional[float] = None
    format: Optional[str] = None
    sample_rate: Optional[int] = None