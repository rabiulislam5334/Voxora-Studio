"""Shared project-session wiring across the desktop production workspaces.

These tests use real Tk widgets but do not require media engines or a display
server; environments without Tk/display support skip cleanly.
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402

from app.core.config import AppConfig  # noqa: E402
from app.models.scene import Scene  # noqa: E402
from app.projects.manager import ProjectManager  # noqa: E402
from app.ui.composition_editor_tab import CompositionEditorTab  # noqa: E402
from app.ui.scene_asset_binding_tab import SceneAssetBindingTab  # noqa: E402
from app.ui.script_panel import ScriptPanel  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402


@pytest.fixture
def shared_workspaces(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")
    root.geometry("1200x760")
    palette = apply_theme(ttk.Style(root), "dark")
    config = AppConfig(root_dir=tmp_path)
    config.ensure_directories()
    manager = ProjectManager()
    refresh_events = []

    scene_assets = None
    composition = None

    def project_changed():
        refresh_events.append(manager.current_project.id)
        scene_assets.refresh_project()
        composition.refresh_project()

    script = ScriptPanel(
        root,
        config=config,
        palette=palette,
        project_manager=manager,
        on_project_changed=project_changed,
        before_project_change=lambda: True,
    )
    scene_assets = SceneAssetBindingTab(
        root, config=config, palette=palette, project_manager=manager,
    )
    composition = CompositionEditorTab(
        root, config=config, palette=palette, project_manager=manager,
    )
    for widget in (script, scene_assets, composition):
        widget.pack(fill="both", expand=True)
    yield root, manager, script, scene_assets, composition, refresh_events
    for widget in (script, scene_assets, composition):
        widget.destroy()
    root.destroy()


def test_script_scene_assets_and_composition_share_one_project_manager(shared_workspaces):
    root, manager, script, scene_assets, composition, _ = shared_workspaces

    assert script._project_manager is manager
    assert scene_assets.project_manager is manager
    assert composition.project_manager is manager

    script._on_new_project()
    project = manager.current_project
    scene = project.add_scene(Scene(title="Shared scene", text="A shared narration."))
    manager.mark_dirty()
    script._rebuild_tree_rows()
    scene_assets.refresh_project()
    composition.refresh_project()
    root.update()

    assert script.get_project() is project
    assert scene_assets.project_manager.current_project is project
    assert composition.project_manager.current_project is project
    assert scene_assets.scene_tree.exists(scene.id)
    assert composition._scene_ids == [scene.id]
    assert "Untitled Project" in scene_assets.project_label.cget("text")


def test_project_replacement_refreshes_both_visual_workspaces(shared_workspaces):
    root, manager, script, scene_assets, composition, refresh_events = shared_workspaces

    first = manager.current_project
    first.add_scene(Scene(title="Old scene"))
    manager.mark_dirty()
    scene_assets.refresh_project()
    composition.refresh_project()
    # This test focuses on workspace refresh, not the discard-confirmation dialog.
    manager.dirty = False

    script._on_new_project()
    root.update()

    assert manager.current_project is not first
    assert refresh_events == [manager.current_project.id]
    assert scene_assets.scene_tree.get_children() == ()
    assert composition._scene_ids == []
    assert scene_assets.project_manager.current_project is manager.current_project
    assert composition.project_manager.current_project is manager.current_project


def test_shared_project_mutations_are_visible_without_reopening(shared_workspaces):
    root, manager, script, scene_assets, composition, _ = shared_workspaces

    script._on_new_project()
    project = manager.current_project
    project.settings["shared_session_probe"] = {"source": "scene-assets"}
    manager.mark_dirty()
    script.refresh_project_status()
    root.update()

    assert composition.project_manager.current_project.settings["shared_session_probe"] == {
        "source": "scene-assets"
    }
    assert "Unsaved changes" in script._status_unsaved_label.cget("text")



def test_unapplied_composition_draft_is_preserved_when_switch_is_cancelled(shared_workspaces, monkeypatch):
    _, _, _, _, composition, _ = shared_workspaces
    import app.ui.composition_editor_tab as module

    composition._composition_dirty = True
    monkeypatch.setattr(module.messagebox, "askyesno", lambda *args, **kwargs: False)
    assert composition.confirm_project_switch() is False
    assert composition._composition_dirty is True

    monkeypatch.setattr(module.messagebox, "askyesno", lambda *args, **kwargs: True)
    assert composition.confirm_project_switch() is True
    # Confirmation alone does not destroy the draft; a successful project
    # replacement triggers refresh_project(), which clears it.
    assert composition._composition_dirty is True
