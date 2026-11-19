"""Drives the real Studio workspace (all tabs) with a fake TTS provider, real
FFmpeg and tiny synthetic media. Skipped without Tk, a display, or FFmpeg."""
from __future__ import annotations

import gc
import os
import subprocess
import time
import threading
from pathlib import Path

import pytest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402

from app.core.async_bridge import AsyncBridge  # noqa: E402
from app.core.config import AppConfig  # noqa: E402
from app.models.scene import Scene  # noqa: E402
from app.projects.manager import ProjectManager  # noqa: E402
from app.studio.models import MusicTrack, SceneVideo, StudioState  # noqa: E402
from app.tts.manager import TTSManager  # noqa: E402
from app.ui.script_panel import ScriptPanel  # noqa: E402
from app.ui.studio_panel import SECTION_TABS, StudioPanel  # noqa: E402
from app.ui.theme import apply_theme  # noqa: E402
from tests.helpers import FakeProvider  # noqa: E402


@pytest.fixture
def studio(tmp_path, real_ffmpeg, tone_mp3, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")
    root.geometry("1250x800")
    palette = apply_theme(ttk.Style(root), "dark")
    config = AppConfig(root_dir=tmp_path)
    config.ensure_directories()
    provider = FakeProvider(tone_mp3, delay=0.02)
    manager = TTSManager()
    manager.register(provider, set_active=True)
    bridge = AsyncBridge()
    script = ScriptPanel(root, config=config, palette=palette)
    panel = StudioPanel(root, tts_manager=manager, async_bridge=bridge, config=config, palette=palette,
                        script_source=script)
    script.grid(row=0, column=0, sticky="nsew")
    panel.grid(row=0, column=0, sticky="nsew")
    dialogs = {"info": [], "yesno": True}
    import app.ui.studio_produce_tab as produce_module
    monkeypatch.setattr(produce_module.messagebox, "showinfo", lambda title, msg, **k: dialogs["info"].append(msg))
    monkeypatch.setattr(produce_module.messagebox, "askyesno", lambda *a, **k: dialogs["yesno"])

    def pump(until, timeout=40.0):
        end = time.time() + timeout
        while time.time() < end:
            bridge.poll()
            root.update()
            if until():
                return True
            time.sleep(0.02)
        return False

    assert pump(lambda: panel.voice.ffmpeg_ready() and str(panel.voice._scene_narration_btn["state"]) == "normal")
    assert pump(lambda: bool(panel.voice._all_voices))
    panel.voice._tree.selection_set("fake-voice")
    panel.voice._on_tree_select()
    panel.voice._current_settings.sentence_pause_ms = 0
    panel.voice._current_settings.scene_pause_ms = 300
    # Pytest retains fixture values in the test item's funcargs until teardown
    # completes. Yield a mutable container so teardown can clear that retained
    # reference as well as releasing the local widget references below.
    resources = [root, script, panel, provider, pump, config, dialogs]
    yield resources
    panel.shutdown()
    bridge.shutdown()
    # Destroy widgets and release Tk-backed variable references on the main
    # thread while the Tcl interpreter is still alive. Otherwise Variable.__del__
    # may run later, after root.destroy(), during cyclic garbage collection.
    panel.destroy()
    script.destroy()
    resources.clear()
    del panel, script
    gc.collect()
    root.destroy()


def png(real_ffmpeg, path: Path, color="blue"):
    subprocess.run([str(real_ffmpeg.require()), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"color=c={color}:s=640x480", "-frames:v", "1", str(path)], check=True)
    return path


def add_scenes(script, *texts):
    out = []
    for i, text in enumerate(texts, start=1):
        out.append(script._project.add_scene(Scene(title=f"Scene {i}", text=text)))
    script._rebuild_tree_rows()
    return out


def test_every_sidebar_section_opens_the_right_tab(studio):
    root, script, panel, *_ = studio
    expected = {"voice": panel.voice, "audio": panel.audio_tab, "scenes": panel.scenes_tab,
                "video": panel.video_tab, "produce": panel.produce_tab,
                "transitions": panel.transitions_tab}
    for section, key in SECTION_TABS.items():
        panel.show_section(section)
        assert panel._notebook.nametowidget(panel._notebook.select()) is expected[key], section
    panel.show_section("Unknown")  # ignored, no crash


def test_settings_changes_are_saved_in_the_project_file_and_restored(studio, tmp_path, real_ffmpeg):
    root, script, panel, provider, pump, config, dialogs = studio
    (scene,) = add_scenes(script, "Hello there.")
    script._select_scene_in_tree(scene.id)
    panel.show_section("Timeline")
    img = png(real_ffmpeg, tmp_path / "ছবি one.png")
    panel.ctx.state.video.set_scene(scene.id, SceneVideo(media_path=str(img), duration_s=6.0, motion="pan_left"))
    panel.ctx.state.video.aspect, panel.ctx.state.video.resolution = "9:16", "1080p"
    panel.ctx.state.audio.tracks.append(MusicTrack(path=str(tmp_path / "m.mp3"), volume_percent=11))
    script._project_manager.dirty = False
    panel.ctx.commit()
    assert script._project_manager.dirty is True       # unsaved-changes tracking sees studio edits
    panel.ctx.commit()                                  # no real change -> still just dirty, no crash

    path = script._project_manager.save(tmp_path / "প্রজেক্ট.voxora")
    other = ProjectManager().open(path)
    restored = StudioState.from_project_settings(other.settings)
    assert restored.to_dict() == panel.ctx.state.to_dict()
    assert restored.video.scene(scene.id).media_path == str(img)
    assert restored.video.size == (1080, 1920)


def test_opening_a_different_project_reloads_studio_settings(studio, tmp_path):
    root, script, panel, provider, pump, config, dialogs = studio
    (scene,) = add_scenes(script, "First project.")
    panel.ctx.state.video.transition = "crossfade"
    panel.ctx.commit()
    script._on_new_project = script._on_new_project  # (kept for readability)
    script._project_manager.new_project("Second")
    assert pump(lambda: panel.ctx.state.video.transition == "cut", timeout=5)   # poll noticed the new project
    assert panel.video_tab._vars["transition"].get() == "cut"


def test_video_tab_edits_update_state_and_size(studio):
    root, script, panel, *_ = studio
    panel.show_section("Video")
    panel.video_tab._vars["aspect"].set("9:16")
    panel.video_tab._vars["resolution"].set("720p")
    panel.video_tab._vars["fps"].set("24")
    panel.video_tab._changed()
    video = panel.ctx.state.video
    assert (video.aspect, video.resolution, video.fps) == ("9:16", "720p", 24)
    assert "720 x 1280" in panel.video_tab._size_label["text"]


def test_scenes_tab_assign_media_shows_thumbnail_and_flags_missing_files(studio, tmp_path, real_ffmpeg, monkeypatch):
    root, script, panel, provider, pump, config, dialogs = studio
    s1, s2 = add_scenes(script, "One scene.", "Another scene.")
    panel.show_section("Timeline")
    tab = panel.scenes_tab
    tab._tree.selection_set(s1.id)
    root.update()
    img = png(real_ffmpeg, tmp_path / "a.png")
    import app.ui.studio_scenes_tab as module
    monkeypatch.setattr(module.filedialog, "askopenfilename", lambda **k: str(img))
    tab._on_assign()
    assert pump(lambda: panel.ctx.state.video.scene(s1.id).media_path == str(img))
    assert pump(lambda: tab._thumb is not None)                           # thumbnail rendered by FFmpeg
    assert tab._tree.item(s1.id, "values")[3] == "ok"
    # a text file is rejected
    bad = tmp_path / "notes.txt"
    bad.write_text("x")
    monkeypatch.setattr(module.filedialog, "askopenfilename", lambda **k: str(bad))
    tab._tree.selection_set(s2.id)
    tab._on_assign()
    assert panel.ctx.state.video.scene(s2.id).media_path is None
    # deleting the file -> MISSING status
    img.unlink()
    tab.refresh()
    assert tab._tree.item(s1.id, "values")[3] == "MISSING"
    # duration / motion editing
    tab._tree.selection_set(s1.id)
    tab._dur_var.set("8")
    tab._motion_var.set("zoom_out")
    tab._on_field_change()
    setting = panel.ctx.state.video.scene(s1.id)
    assert setting.duration_s == 8.0 and setting.motion == "zoom_out"


def test_audio_tab_add_music_edit_trim_waveform_and_mix_preview(studio, tmp_path, real_ffmpeg, monkeypatch):
    root, script, panel, provider, pump, config, dialogs = studio
    music = tmp_path / "bg.mp3"
    subprocess.run([str(real_ffmpeg.require()), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=330:duration=4", "-ac", "2", str(music)], check=True)
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio")
    import app.ui.studio_audio_tab as module
    monkeypatch.setattr(module.filedialog, "askopenfilenames", lambda **k: [str(music), str(junk)])
    panel.show_section("Audio")
    tab = panel.audio_tab
    tab._on_add()
    assert pump(lambda: len(panel.ctx.state.audio.tracks) == 1)
    assert "junk.mp3" in tab._status["text"]                               # unreadable file reported, not added
    track = panel.ctx.state.audio.tracks[0]
    assert pump(lambda: tab._wave_image is not None)                       # waveform drawn in the background
    # trim using the playhead position
    tab._player.play(0.0)
    tab._player.seek(1.0)
    tab._trim_here("start")
    tab._player.seek(3.0)
    tab._trim_here("end")
    assert (track.trim_start_s, track.trim_end_s) == pytest.approx((1.0, 3.0), abs=0.3)
    tab._trim_here("clear")
    assert (track.trim_start_s, track.trim_end_s) == (0.0, None)
    # volume slider persists
    tab._nvol.set(80)
    assert panel.ctx.state.audio.narration_volume_percent == 80
    # mix preview needs narration first
    tab._on_preview_mix()
    assert "Generate narration first" in tab._status["text"]
    (scene,) = add_scenes(script, "Narrate this.")
    script._select_scene_in_tree(scene.id)
    panel.voice._scene_narration_btn.invoke()
    assert pump(lambda: panel.voice.current_narration_wav() is not None)
    tab._on_preview_mix()
    assert pump(lambda: "Mix preview ready" in tab._status["text"])
    assert tab._source_var.get().startswith("Mix preview")


def test_produce_validation_blocks_and_explains_problems(studio, tmp_path):
    root, script, panel, provider, pump, config, dialogs = studio
    (scene,) = add_scenes(script, "Text.")
    panel.ctx.state.video.set_scene(scene.id, SceneVideo(media_path=str(tmp_path / "gone.png")))
    panel.ctx.state.audio.tracks.append(MusicTrack(path=str(tmp_path / "gone.mp3")))
    panel.show_section("Produce")
    tab = panel.produce_tab
    tab._folder_var.set(str(tmp_path / "out"))
    tab._on_start()
    messages = [tab._issues.item(i, "values")[1] for i in tab._issues.get_children()]
    assert any("Music file is missing" in m for m in messages)
    assert any("media file is missing" in m for m in messages)
    assert not tab.running and provider.texts == []                       # nothing was generated


def test_full_production_renders_mp4_from_the_ui_and_reuses_work(studio, tmp_path, real_ffmpeg):
    root, script, panel, provider, pump, config, dialogs = studio
    s1, s2, s3 = add_scenes(script, "Opening line.", "Second scene text.", "")
    img = png(real_ffmpeg, tmp_path / "a.png")
    panel.ctx.state.video.resolution = "360p (draft)"
    panel.ctx.state.video.fps = 15
    panel.ctx.state.video.set_scene(s1.id, SceneVideo(media_path=str(img)))
    panel.ctx.state.video.set_scene(s2.id, SceneVideo(media_path=str(img), motion="pan_right"))
    panel.ctx.state.video.default_duration_s = 1.0
    panel.ctx.commit()
    panel.show_section("Produce")
    tab = panel.produce_tab
    out_dir = tmp_path / "ফলাফল folder"
    tab._folder_var.set(str(out_dir))
    tab._name_var.set("My Video")
    tab._audio_var.set(True)
    tab._format_var.set("mp3")

    tab._on_start()
    assert tab.running and panel.voice.is_busy()
    assert str(panel.voice._full_narration_btn["state"]) == "disabled"      # no parallel narration while producing
    assert pump(lambda: not tab.running)
    mp4, mp3 = out_dir / "My Video.mp4", out_dir / "My Video.mp3"
    assert mp4.exists() and mp3.exists() and not list(out_dir.glob("*.part"))
    info = real_ffmpeg.probe(mp4)
    assert info.kind == "video" and (info.width, info.height) == (640, 360) and info.has_audio
    assert dialogs["info"] and str(mp4) in dialogs["info"][0]
    assert tab._stage["text"] == "Finished" and float(tab._progress["value"]) == 100
    assert not panel.voice.is_busy() and str(panel.voice._full_narration_btn["state"]) == "normal"
    assert s1.id in panel.ctx.known_durations                                # real narration length remembered
    calls = len(provider.texts)

    # second run: nothing regenerated (cache), asks before replacing the existing files
    asked = []
    import app.ui.studio_produce_tab as module
    module.messagebox.askyesno = lambda *a, **k: asked.append(a) or True
    tab._on_start()
    assert pump(lambda: not tab.running)
    assert any("already exist" in str(a) for a in asked)
    assert len(provider.texts) == calls
    assert "2 reused" in tab._message["text"] or "3 reused" in tab._message["text"]


def test_overwrite_is_refused_when_the_user_says_no(studio, tmp_path, real_ffmpeg):
    root, script, panel, provider, pump, config, dialogs = studio
    add_scenes(script, "Some text.")
    panel.show_section("Produce")
    tab = panel.produce_tab
    tab._folder_var.set(str(tmp_path))
    tab._name_var.set("exists")
    (tmp_path / "exists.mp4").write_bytes(b"precious")
    dialogs["yesno"] = False
    tab._on_start()
    assert not tab.running and (tmp_path / "exists.mp4").read_bytes() == b"precious"


def test_cancel_from_the_ui_leaves_no_output(studio, tmp_path, real_ffmpeg):
    root, script, panel, provider, pump, config, dialogs = studio
    provider.delay = 0.3
    add_scenes(script, " ".join(f"Sentence number {i}." for i in range(8)))
    panel.ctx.state.video.resolution = "360p (draft)"
    panel.show_section("Produce")
    tab = panel.produce_tab
    tab._folder_var.set(str(tmp_path / "o"))
    tab._name_var.set("cancelme")
    panel.voice._current_settings.sentence_pause_ms = 100   # one request per sentence -> long enough to cancel
    tab._on_start()
    assert pump(lambda: tab.running and len(provider.texts) >= 1, timeout=10)
    tab._cancel_btn.invoke()
    assert pump(lambda: not tab.running)
    assert tab._stage["text"] == "Cancelled"
    assert not list((tmp_path / "o").glob("cancelme*"))
    assert not list(config.temp_dir.glob("production_*"))
    assert str(panel.voice._full_narration_btn["state"]) == "normal"


def test_audio_tab_export_final_audio_runs_an_audio_only_production(studio, tmp_path, monkeypatch):
    root, script, panel, provider, pump, config, dialogs = studio
    add_scenes(script, "Export just the audio.")
    panel.show_section("Audio")
    target = tmp_path / "exports" / "only audio.wav"
    import app.ui.studio_produce_tab as module
    monkeypatch.setattr(module.filedialog, "asksaveasfilename", lambda **k: str(target))
    panel.audio_tab._ctx.export_audio()
    assert pump(lambda: target.exists() and not panel.produce_tab.running)
    assert not (tmp_path / "exports" / "only audio.mp4").exists()


def test_main_window_starts_with_all_sections_and_closes(tmp_path, monkeypatch, real_ffmpeg):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")
    from app.core import config as config_module
    cfg = AppConfig(root_dir=tmp_path)
    cfg.ensure_directories()
    monkeypatch.setattr(config_module, "_config", cfg)
    from app.ui.main_window import MainWindow
    from app.ui.sidebar import Sidebar
    window = MainWindow(root)
    for _ in range(30):
        root.update()
        time.sleep(0.02)
    assert {"Voice", "Audio", "Timeline", "Video", "Produce"} <= set(Sidebar.NAV_ITEMS)
    studio = window._pages["Voice"]
    assert all(window._pages[n] is studio for n in ("Audio", "Timeline", "Video", "Produce"))
    for name in ("Dashboard", "Script", "Voice", "Audio", "Timeline", "Video", "Produce", "Subtitles", "Settings"):
        window._show_page(name)
        root.update()

    # All project-aware pages must point at the same application-owned manager.
    script = window._pages["Script"]
    scene_assets = window._pages["Scene Assets"]
    composition = window._pages["Composition"]
    assert script._project_manager is window.project_session.manager
    assert scene_assets.project_manager is window.project_session.manager
    assert composition.project_manager is window.project_session.manager

    script._on_new_project()
    shared_scene = script._project.add_scene(Scene(title="Shared session scene"))
    script._project_manager.mark_dirty()
    script._rebuild_tree_rows()
    window._show_page("Scene Assets")
    window._show_page("Composition")
    assert scene_assets.project_manager.current_project is script._project
    assert composition.project_manager.current_project is script._project
    assert scene_assets.scene_tree.exists(shared_scene.id)
    assert shared_scene.id in composition._scene_ids

    # Deleting the scene currently being edited in Composition must ask before
    # discarding editor-only layout changes.
    composition._active_scene_id = shared_scene.id
    composition._composition_dirty = True
    monkeypatch.setattr("app.ui.main_window.messagebox.askyesno", lambda *args, **kwargs: False)
    assert window.project_session.can_delete_scene(shared_scene.id) is False
    monkeypatch.setattr("app.ui.main_window.messagebox.askyesno", lambda *args, **kwargs: True)
    assert window.project_session.can_delete_scene(shared_scene.id) is True
    composition._composition_dirty = False

    # Dashboard actions delegate to the real Script workspace; the top-bar shortcut opens Produce.
    routed = []
    original_new, original_open = script._on_new_project, script._on_open_project
    script._on_new_project = lambda: routed.append("new")
    script._on_open_project = lambda: routed.append("open")
    window._on_new_project()
    assert window._current_page == "Script" and routed == ["new"]
    window._on_open_project()
    assert window._current_page == "Script" and routed == ["new", "open"]
    script._on_new_project, script._on_open_project = original_new, original_open
    window._on_export()
    assert window._current_page == "Produce"
    assert window._pages["Produce"]._notebook.nametowidget(window._pages["Produce"]._notebook.select()) is window._pages["Produce"].produce_tab
    assert window.project_label.cget("text") == script._project.name
    window._toggle_theme()
    window._toggle_theme()
    window._on_close()


def test_composition_editor_renders_still_png_from_managed_bound_asset(tmp_path, monkeypatch, real_ffmpeg):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"No display available: {exc}")
    from app.core import config as config_module
    from app.universal.composition import CompositionCanvas, CompositionElement, SceneComposition, VisualTransform
    from app.universal.composition_workflow import preview_scene_composition
    from app.universal.models import AssetRef, ScenePlan
    from PIL import Image

    cfg = AppConfig(root_dir=tmp_path)
    cfg.ensure_directories()
    monkeypatch.setattr(config_module, "_config", cfg)
    from app.ui.main_window import MainWindow
    window = MainWindow(root)
    try:
        script = window._pages["Script"]
        script._on_new_project()
        scene = script._project.add_scene(Scene(title="Raster UI scene", text="Still image test"))
        script._project_manager.mark_dirty()
        source = png(real_ffmpeg, tmp_path / "bound-source.png", color="red")
        editor = window._pages["Composition"]
        asset = editor.library.import_file(source)
        plan = ScenePlan(scene_id=scene.id, asset_refs=[AssetRef(
            asset_id=asset.asset_id, kind=asset.kind, path=asset.location, identity=asset.content_sha256,
        )])
        script._project.settings["universal"] = {
            "format_version": 1, "profile_id": None, "scene_plans": {scene.id: plan.to_dict()},
        }
        composition = SceneComposition(
            composition_id=f"composition-{scene.id}", scene_id=scene.id, canvas=CompositionCanvas(32, 16),
            elements=(CompositionElement(element_id="ui-render-element", asset_id=asset.asset_id,
                transform=VisualTransform(x=0, y=0, width=1, height=1), fit_mode="stretch"),),
        )
        preview = preview_scene_composition(script._project, composition)
        assert preview.is_valid
        output = editor._render_png_worker(
            script._project, composition, preview, tmp_path / "ui-composition.png", threading.Event(),
        )
        assert output.is_file() and output.stat().st_size > 0
        with Image.open(output) as rendered:
            assert rendered.format == "PNG" and rendered.size == (32, 16)
            assert rendered.getpixel((16, 8))[:3] == (255, 0, 0)
        assert editor._render_button.cget("text") == "Render Still PNG…"
    finally:
        window._on_close()
