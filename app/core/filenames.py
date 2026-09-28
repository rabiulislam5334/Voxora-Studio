from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_filename(base: str, extension: str, max_length: int = 60) -> str:
    """Build a Windows-safe, collision-free filename from arbitrary text.

    - Strips characters illegal in Windows filenames (keeps Unicode/Bengali
      letters -- NTFS handles those fine).
    - Collapses whitespace to underscores.
    - Appends a UTC timestamp + short UUID so results never overwrite an
      existing file and callers don't need their own uniqueness scheme.
    - Falls back to "voice" if nothing usable remains after cleaning.
    """
    normalized = unicodedata.normalize("NFC", base or "").strip()
    normalized = _UNSAFE_CHARS.sub("", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = normalized.strip("._")
    if not normalized:
        normalized = "voice"
    normalized = normalized[:max_length]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    unique = uuid.uuid4().hex[:6]
    ext = extension.lstrip(".")
    return f"{normalized}_{timestamp}_{unique}.{ext}"