"""Application-owned project session shared by all project-aware UI pages.

The session deliberately wraps the existing ProjectManager rather than changing
project persistence. This preserves .voxora serialization, revision tracking,
file-stamp conflict detection, and backup behavior.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from app.projects.manager import ProjectManager


class ProjectSession:
    """Own one ProjectManager and coordinate safe project replacement."""

    def __init__(self, manager: Optional[ProjectManager] = None) -> None:
        self.manager = manager or ProjectManager()
        self._change_guards: List[Callable[[], bool]] = []

    def add_change_guard(self, guard: Callable[[], bool]) -> None:
        if guard not in self._change_guards:
            self._change_guards.append(guard)

    def can_replace_project(self) -> bool:
        """Return False when a page has uncommitted editor-only work."""
        for guard in tuple(self._change_guards):
            try:
                if not guard():
                    return False
            except Exception:
                # A failed guard must fail closed; replacing a project could
                # otherwise silently discard work from another page.
                return False
        return True
