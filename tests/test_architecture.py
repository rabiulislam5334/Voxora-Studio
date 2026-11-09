"""Layering guard: the persistence package must stay independent of the UI and workers."""
from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = ("app.ui", "app.workers", "app.projects.manager", "tkinter")


def test_persistence_package_has_no_forbidden_imports():
    root = Path(__file__).resolve().parents[1] / "app" / "persistence"
    offenders = []
    for path in sorted(root.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name == "tkinter" or any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                    offenders.append(f"{path.name}: {name}")
    assert offenders == []
