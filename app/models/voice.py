from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Voice:
    id: str
    name: str
    provider: str
    language: str
    gender: Optional[str] = None
    metadata: dict = field(default_factory=dict)