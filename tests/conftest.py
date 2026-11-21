from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import app.core.config as config_module
from app.audio.ffmpeg_tool import FFmpegTool
from app.core.config import AppConfig
from app.core.settings_store import SettingsStore


@pytest.fixture(scope="session")
def real_ffmpeg(tmp_path_factory):
    """A verified FFmpegTool, or skip the test when FFmpeg is unavailable."""
    settings = SettingsStore(tmp_path_factory.mktemp("settings") / "settings.json")
    tool = FFmpegTool(settings)
    status = tool.detect()
    if not status.available:
        pytest.skip(f"FFmpeg not available: {status.message}")
    return tool


@pytest.fixture(scope="session")
def tone_mp3(real_ffmpeg, tmp_path_factory) -> Path:
    """0.5 s 24 kHz mono MP3 used by fake TTS providers."""
    path = tmp_path_factory.mktemp("tone") / "tone.mp3"
    exe = str(real_ffmpeg.require())
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=0.5:sample_rate=24000", "-ac", "1",
         "-c:a", "libmp3lame", "-b:a", "48k", str(path)],
        check=True,
    )
    return path


@pytest.fixture(scope="session")
def tone_pcm(real_ffmpeg, tmp_path_factory) -> Path:
    """Exact 0.5 s PCM fixture for production timing tests.

    MP3 encoder delay/padding can be exposed differently by FFmpeg builds on
    Windows and Linux. ProductionJob tests need a codec-independent narration
    duration so they test timeline/render behavior rather than MP3 gapless
    metadata. The separate tone_mp3 fixture remains available for MP3 tests.
    """
    path = tmp_path_factory.mktemp("tone_pcm") / "tone.wav"
    exe = str(real_ffmpeg.require())
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=0.5:sample_rate=24000", "-ac", "1",
         "-ar", "24000", "-c:a", "pcm_s16le", "-f", "wav", str(path)],
        check=True,
    )
    return path


@pytest.fixture(autouse=True)
def isolated_app_config(tmp_path_factory, monkeypatch):
    """ProjectManager() now keeps rolling backups under AppConfig.backups_dir.
    Point the config singleton at a per-test temp root (a sibling of the
    test's own tmp_path, so folder-listing assertions never see it) so no test ever writes
    into the developer's real ``userdata/`` folder. Nothing is created until a
    backup is actually written."""
    monkeypatch.setattr(config_module, "_config", AppConfig(root_dir=tmp_path_factory.mktemp("app_root")))
