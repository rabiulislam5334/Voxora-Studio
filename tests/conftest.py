from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.audio.ffmpeg_tool import FFmpegTool
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
    """0.5 s 24 kHz mono sine MP3 -- stands in for a provider's output."""
    path = tmp_path_factory.mktemp("tone") / "tone.mp3"
    exe = str(real_ffmpeg.require())
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=0.5:sample_rate=24000", "-ac", "1",
         "-c:a", "libmp3lame", "-b:a", "48k", str(path)],
        check=True,
    )
    return path