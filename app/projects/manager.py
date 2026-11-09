from __future__ import annotations

import itertools
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import get_config
from app.core.exceptions import ProjectError
from app.core.logger import get_logger
from app.models.project import Project
from app.persistence.backups import BackupStore
from app.persistence.repository import JsonProjectRepository, ProjectRepository
from app.persistence.stamps import FileStamp

logger = get_logger("projects.manager")

PROJECT_EXTENSION = ".voxora"

# Process-wide, strictly increasing. Every change to a project (and every
# project replacement) gets a fresh number, so "which of two states is newer"
# never depends on a per-project counter that could restart.
_REVISIONS = itertools.count(1)


def _default_repository() -> ProjectRepository:
    """The application repository: JSON files with rolling backups stored under
    ``AppConfig.backups_dir`` (``userdata/backups``)."""
    return JsonProjectRepository(BackupStore(get_config().backups_dir))


def _same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


@dataclass(frozen=True)
class SaveResult:
    """What the last successful save wrote. ``revision`` is the project
    revision that was serialized into the file."""

    path: Path
    revision: int
    stamp: FileStamp
    backup_path: Optional[Path]


class ProjectManager:
    """Owns the currently open Project, its on-disk path (if any), and
    whether it has unsaved changes. File I/O is delegated to a
    ``ProjectRepository`` (UTF-8 JSON, atomic replace, disk-stamp conflict
    check, optional rolling backups), so a crash or power loss mid-save can
    never leave a corrupted or half-written project file behind.

    ``revision`` increases on every ``mark_dirty()`` and whenever the project
    is replaced; ``saved_revision`` is the revision of the state that is on
    disk. A snapshot payload is *stale* when its revision is not greater than
    the revision a successful save wrote -- never decided by sequence numbers.
    """

    def __init__(self, repository: Optional[ProjectRepository] = None) -> None:
        self._repository: ProjectRepository = repository if repository is not None else _default_repository()
        self.current_project: Project = Project()
        self.current_path: Optional[Path] = None
        self.dirty: bool = False
        self.revision: int = next(_REVISIONS)
        self.saved_revision: int = self.revision
        self.last_save: Optional[SaveResult] = None
        # Stamp of the file as last read/written by this manager, and the
        # path it belongs to (the conflict check applies to that path only).
        self._stamp: Optional[FileStamp] = None
        self._stamp_path: Optional[Path] = None

    # ------------------------------------------------------------ state changes

    def new_project(self, name: str = "Untitled Project") -> Project:
        project = Project(name=name)
        revision = next(_REVISIONS)
        self.current_project = project
        self.current_path = None
        self.dirty = False
        self.revision = revision
        self.saved_revision = revision
        self.last_save = None
        self._stamp = None
        self._stamp_path = None
        return project

    def mark_dirty(self) -> None:
        self.revision = next(_REVISIONS)
        self.dirty = True

    def ensure_dirty_revision(self) -> bool:
        """Fail-safe for autosave: a dirty project must always have a
        revision newer than the saved one. If some code path set ``dirty``
        without going through ``mark_dirty()``, bump the revision so the
        state is never treated as already saved. Returns True if it bumped."""
        if self.dirty and self.revision <= self.saved_revision:
            self.revision = next(_REVISIONS)
            logger.warning("Dirty project had a stale revision; bumped to %d", self.revision)
            return True
        return False

    def adopt(self, project: Project, path: Optional[Path] = None, dirty: bool = True) -> None:
        """Install an already-built project (e.g. a recovered one) without
        touching the file system. The recovered state counts as *newer* than
        anything saved when ``dirty`` is True."""
        revision = next(_REVISIONS)
        new_path = Path(path) if path is not None else None
        self.current_project = project
        self.current_path = new_path
        self.dirty = bool(dirty)
        self.revision = revision
        self.saved_revision = revision - 1 if dirty else revision
        self.last_save = None
        self._stamp = None
        self._stamp_path = None

    def serialize_snapshot(self) -> Tuple[bytes, int]:
        """The current project as file bytes together with the revision they
        represent, read in one call so they can never disagree. Does not touch
        ``updated_at`` and writes nothing."""
        revision = self.revision
        return self._repository.serialize(self.current_project), revision

    # -------------------------------------------------------------------- save

    def save(
        self, path: Optional[Path] = None, *, allow_without_backup: bool = False
    ) -> Path:
        target = Path(path) if path is not None else self.current_path
        if target is None:
            raise ProjectError("No destination path given to save the project to.")
        if target.suffix.lower() != PROJECT_EXTENSION:
            target = target.with_suffix(PROJECT_EXTENSION)

        self.current_project.touch()
        revision_at_save = self.revision

        expected = None
        if self._stamp is not None and self._stamp_path is not None:
            if _same_path(self._stamp_path, target):
                expected = self._stamp

        # Raises ProjectError (or a subclass) on any failure; in that case
        # nothing below runs, so dirty / current_path / revision are untouched.
        outcome = self._repository.save(
            self.current_project,
            target,
            expected_stamp=expected,
            allow_without_backup=allow_without_backup,
        )

        self.current_path = outcome.path
        self._stamp = outcome.stamp
        self._stamp_path = outcome.path
        self.saved_revision = revision_at_save
        self.dirty = self.revision > revision_at_save
        self.last_save = SaveResult(
            path=outcome.path,
            revision=revision_at_save,
            stamp=outcome.stamp,
            backup_path=outcome.backup_path,
        )
        logger.info("Saved project to %s", outcome.path)
        return outcome.path

    # -------------------------------------------------------------------- open

    def open(self, path: Path) -> Project:
        path = Path(path)
        result = self._repository.load(path)  # raises ProjectError; nothing changed yet

        revision = next(_REVISIONS)
        self.current_project = result.project
        self.current_path = path
        self.dirty = False
        self.revision = revision
        self.saved_revision = revision
        self.last_save = None
        self._stamp = result.stamp
        self._stamp_path = path
        logger.info("Opened project from %s (%d scenes)", path, len(result.project.scenes))
        return result.project
