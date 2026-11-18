from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")
from tkinter import ttk

from app.core.async_bridge import AsyncBridge
from app.core.config import AppConfig
from app.tts.manager import TTSManager
from app.ui.channel_profile_tab import ChannelProfileTab
from app.ui.script_panel import ScriptPanel
from app.ui.theme import apply_theme


def test_channel_profile_tab_preview_and_explicit_apply(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")
    root.withdraw()
    palette = apply_theme(ttk.Style(root), "dark")
    config = AppConfig(root_dir=tmp_path)
    config.ensure_directories()
    script = ScriptPanel(root, config=config, palette=palette)
    bridge = AsyncBridge()
    context = type("Context", (), {})()
    context.script = script
    context.palette = palette
    context.project = script.get_project
    tab = ChannelProfileTab(root, context)
    try:
        tab._profile_var.set("Rihvaya")
        tab._on_profile_changed()
        tab._preset_var.set("Islamic Documentary")
        tab._render_preview()
        assert "respectful_documentary_illustration" in tab._defaults.cget("text")
        assert "PROFILE" not in tab._diagnostics.get("1.0", "end").upper() or "PROFILE" in tab._diagnostics.get("1.0", "end").upper()

        asked = []
        import app.ui.channel_profile_tab as module
        monkeypatch.setattr(module.messagebox, "askyesno", lambda *a, **k: asked.append(True) or True)
        tab._apply()
        assert asked == [True]
        from app.universal.models import UniversalState
        state = UniversalState.from_project_settings(script.get_project().settings)
        assert state.profile_id == "rihvaya"
        assert state.profile_snapshot.selected_preset_id == "islamic_documentary"
        assert "studio" not in script.get_project().settings
    finally:
        tab.destroy()
        script.destroy()
        bridge.shutdown()
        root.destroy()
