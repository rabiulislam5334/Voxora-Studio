from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional

from app.core.exceptions import ProjectError
from app.core.logger import get_logger
from app.models.project import Project
from app.projects.serializer import project_from_dict, project_to_dict

logger = get_logger("projects.manager")

PROJECT_EXTENSION = ".voxora"


class ProjectManager:
    """Owns the currently open Project, its on-disk path (if any), and
    whether it has unsaved changes. All file I/O is UTF-8 JSON with an
    atomic write (temp file in the same directory, then replaced into
    place) so a crash or power loss mid-save can never leave a corrupted
    or half-written project file behind.
    """

    def __init__(self) -> None:
        self.current_project: Project = Project()
        self.current_path: Optional[Path] = None
        self.dirty: bool = False

    def new_project(self, name: str = "Untitled Project") -> Project:
        self.current_project = Project(name=name)
        self.current_path = None
        self.dirty = False
        return self.current_project

    def mark_dirty(self) -> None:
        self.dirty = True

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path is not None else self.current_path
        if target is None:
            raise ProjectError("No destination path given to save the project to.")
        if target.suffix.lower() != PROJECT_EXTENSION:
            target = target.with_suffix(PROJECT_EXTENSION)

        self.current_project.touch()
        data = project_to_dict(self.current_project)

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                dir=str(target.parent), prefix=".voxora_tmp_", suffix=".json"
            )
            tmp_path = Path(tmp_name)
            try:
                with open(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                tmp_path.replace(target)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            logger.exception("Failed to save project to %s", target)
            raise ProjectError(f"Could not save the project: {exc}") from exc

        self.current_path = target
        self.dirty = False
        logger.info("Saved project to %s", target)
        return target

    def open(self, path: Path) -> Project:
        path = Path(path)
        if not path.exists():
            raise ProjectError(f"Project file not found: {path}")

        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectError(f"Could not read project file: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProjectError(
                f"'{path.name}' is not a valid Voxora Studio project file (invalid JSON): {exc}"
            ) from exc

        project = project_from_dict(data)  # raises ProjectError on structural problems

        self.current_project = project
        self.current_path = path
        self.dirty = False
        logger.info("Opened project from %s (%d scenes)", path, len(project.scenes))
        return project