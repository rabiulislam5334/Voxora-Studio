"""Project repository: the one place that reads and writes ``.voxora`` bytes.

``JsonProjectRepository`` owns the on-disk format (UTF-8 JSON, same layout and
platform newline behaviour as before), atomic replacement, the disk-stamp
conflict check and rolling backups. ``ProjectManager`` delegates to it.

Save order (every step that can fail happens *before* the target is touched):

 1. serialize the project (a ``TypeError`` from unserializable settings
    propagates unchanged, before any file is created);
 2. write + fsync a temp file next to the target;
 3. if the target exists: read and hash it (verification 1). When the caller
    passes the stamp from its last open/save and the content differs, raise
    ``ProjectConflictError``. If the caller passes a stamp but the target no
    longer exists, that is also a ``ProjectConflictError`` (the file is never
    silently recreated);
 4. write a rolling backup from those verified bytes. A failure raises
    ``ProjectBackupError`` unless the caller explicitly allows saving without
    a backup;
 5. hash the target again (verification 2) -- this narrows the window in
    which another writer could slip in;
 6. replace the target (4 attempts on ``PermissionError``, see ``atomic``).

Known limitation (documented, not hidden): there is no atomic
compare-and-swap rename on Windows, so a writer that lands between
verification 2 and the replace (milliseconds) still wins silently. The locks
planned for a later step do not cover other machines or programs either.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from app.core.exceptions import ProjectBackupError, ProjectConflictError, ProjectError
from app.core.logger import get_logger
from app.models.project import Project
from app.persistence.atomic import stage_write
from app.persistence.backups import BackupError, BackupStore
from app.persistence.stamps import FileStamp, read_stamped, stamp_of_written
from app.projects.serializer import project_from_dict, project_to_dict

logger = get_logger("persistence.repository")


@dataclass(frozen=True)
class LoadResult:
    project: Project
    stamp: FileStamp


@dataclass(frozen=True)
class SaveOutcome:
    path: Path
    stamp: FileStamp
    backup_path: Optional[Path]


class ProjectRepository(Protocol):
    def serialize(self, project: Project) -> bytes: ...

    def load(self, path: Path) -> LoadResult: ...

    def save(
        self,
        project: Project,
        path: Path,
        *,
        expected_stamp: Optional[FileStamp] = None,
        allow_without_backup: bool = False,
    ) -> SaveOutcome: ...


class JsonProjectRepository:
    def __init__(
        self,
        backup_store: Optional[BackupStore] = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._backup_store = backup_store
        self._sleep = sleep

    # ------------------------------------------------------------------ format

    def serialize(self, project: Project) -> bytes:
        text = json.dumps(project_to_dict(project), ensure_ascii=False, indent=2)
        # Text-mode files used to translate "\n" to the platform newline
        # (CRLF on Windows). Keep exactly that, so saved bytes are unchanged.
        return text.replace("\n", os.linesep).encode("utf-8")

    # -------------------------------------------------------------------- load

    def load(self, path: Path) -> LoadResult:
        path = Path(path)
        if not path.exists():
            raise ProjectError(f"Project file not found: {path}")

        try:
            raw, stamp = read_stamped(path)
        except OSError as exc:
            raise ProjectError(f"Could not read project file: {exc}") from exc

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProjectError(
                f"'{path.name}' is not valid UTF-8 text and cannot be read as a "
                f"Voxora Studio project file: {exc}"
            ) from exc

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProjectError(
                f"'{path.name}' is not a valid Voxora Studio project file (invalid JSON): {exc}"
            ) from exc

        project = project_from_dict(data)  # raises ProjectError on structural problems
        return LoadResult(project=project, stamp=stamp)

    # -------------------------------------------------------------------- save

    def save(
        self,
        project: Project,
        path: Path,
        *,
        expected_stamp: Optional[FileStamp] = None,
        allow_without_backup: bool = False,
    ) -> SaveOutcome:
        target = Path(path)
        data = self.serialize(project)  # no file I/O yet

        backup_path: Optional[Path] = None
        try:
            with stage_write(target, data, sleep=self._sleep) as staged:
                existing = self._read_existing(target)
                if existing is None:
                    # Opened/saved here before, but the file is gone now:
                    # never silently recreate it (see _deleted_conflict).
                    if expected_stamp is not None:
                        raise self._deleted_conflict(target, expected_stamp)
                else:
                    old_bytes, old_stamp = existing
                    self._check_unchanged(target, expected_stamp, old_stamp)  # verification 1
                    backup_path = self._backup(project, target, old_bytes, allow_without_backup)
                    if expected_stamp is not None:
                        again = self._read_existing(target)
                        if again is None:
                            raise self._deleted_conflict(target, expected_stamp)
                        self._check_unchanged(target, expected_stamp, again[1])  # verification 2
                staged.commit()
        except ProjectError:
            raise
        except OSError as exc:
            logger.exception("Failed to save project to %s", target)
            raise ProjectError(f"Could not save the project: {exc}") from exc

        return SaveOutcome(path=target, stamp=stamp_of_written(target, data), backup_path=backup_path)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _read_existing(target: Path):
        try:
            return read_stamped(target)
        except FileNotFoundError:
            return None

    @staticmethod
    def _deleted_conflict(target: Path, expected: FileStamp) -> ProjectConflictError:
        return ProjectConflictError(
            f"'{target.name}' was deleted or moved on disk (by another window or program) "
            f"after it was opened or last saved here ({expected.describe()}). "
            "Nothing was written. Use Save As to keep your changes under a new name."
        )

    @staticmethod
    def _check_unchanged(target: Path, expected: Optional[FileStamp], current: FileStamp) -> None:
        if expected is None or expected.same_content(current):
            return
        raise ProjectConflictError(
            f"'{target.name}' was changed on disk (by another window or program) after "
            f"it was opened or last saved here ({expected.describe()} -> {current.describe()}). "
            "Nothing was overwritten. Use Save As to keep your changes under a new name."
        )

    def _backup(
        self, project: Project, target: Path, old_bytes: bytes, allow_without_backup: bool
    ) -> Optional[Path]:
        if self._backup_store is None:
            return None
        try:
            return self._backup_store.create_from_bytes(project.id, target.stem, old_bytes)
        except BackupError as exc:
            if allow_without_backup:
                logger.warning("Saving %s without a backup: %s", target, exc)
                return None
            raise ProjectBackupError(
                f"Could not back up the existing '{target.name}' before overwriting it ({exc}). "
                "The project was not saved and the original file is unchanged."
            ) from exc
