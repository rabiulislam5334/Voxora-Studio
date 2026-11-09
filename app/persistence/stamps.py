"""Disk stamps: a cheap, strong "has this file changed?" check.

A stamp is ``(mtime_ns, size, sha256)``. **Only the SHA-256 decides**
whether the content changed. mtime and size are kept for diagnostics (a sync
tool merely touching a file must not look like a conflict).
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


@dataclass(frozen=True)
class FileStamp:
    mtime_ns: int
    size: int
    sha256: str

    def same_content(self, other: "FileStamp") -> bool:
        return self.sha256 == other.sha256

    def describe(self) -> str:
        return f"{self.size} bytes, sha256 {self.sha256[:12]}"


def stamp_from_bytes(data: bytes, mtime_ns: int = 0) -> FileStamp:
    return FileStamp(mtime_ns=mtime_ns, size=len(data), sha256=hashlib.sha256(data).hexdigest())


def read_stamped(path: Path) -> Tuple[bytes, FileStamp]:
    """Read a whole file and stamp exactly the bytes that were read."""
    with open(path, "rb") as handle:
        data = handle.read()
        mtime_ns = os.fstat(handle.fileno()).st_mtime_ns
    return data, stamp_from_bytes(data, mtime_ns)


def stamp_of_written(path: Path, data: bytes) -> FileStamp:
    """Stamp for a file this process just wrote: hash of the bytes written,
    mtime taken from the file system (0 if it cannot be read)."""
    try:
        mtime_ns = Path(path).stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    return stamp_from_bytes(data, mtime_ns)
