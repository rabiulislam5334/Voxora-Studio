from __future__ import annotations

import re
from pathlib import Path
from typing import List

from app.core.exceptions import ProjectError


def import_txt_file(path: Path) -> str:
    """Read a UTF-8 text file. Raises ProjectError with a clear message on
    anything else (wrong encoding, missing file, permission error) --
    callers should never need to catch raw OSError/UnicodeDecodeError."""
    path = Path(path)
    if not path.exists():
        raise ProjectError(f"File not found: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProjectError(
            f"'{path.name}' could not be read as UTF-8 text. "
            "Please re-save it as UTF-8 and try again."
        ) from exc
    except OSError as exc:
        raise ProjectError(f"Could not read '{path.name}': {exc}") from exc


def split_into_scenes(text: str) -> List[str]:
    """Split on blank-line boundaries (one or more blank lines, tolerant of
    trailing whitespace on the blank line itself). Each resulting block
    keeps its own internal line breaks intact -- sentences are never split,
    and fully empty sections are dropped."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n[ \t]*\n+", normalized)
    return [b.strip() for b in blocks if b.strip()]