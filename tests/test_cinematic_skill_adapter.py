from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.universal.cinematic_skill_adapter import (
    CinematicSkillRenderCancelledError,
    CinematicSkillRenderCoordinator,
    CinematicSkillRenderError,
    CinematicSkillUnavailableError,
)


class FakeFilm:
    duration = 0.2
    fps = 10


class FakeRenderer:
    def __init__(self, film, *, width, height, doc=None):
        self.width = width
        self.height = height

    def frame(self, index):
        return Image.new("RGB", (self.width, self.height), (index * 20, 40, 80))


class FakeEncoder:
    def __init__(self):
        self.sequence = None

    def encode(self, sequence, destination, *, on_progress=None, cancel=None):
        self.sequence = sequence
        Path(destination).write_bytes(b"verified-by-fake-encoder")
        if on_progress:
            on_progress(1.0)
        return SimpleNamespace(codec="h264")


def test_renders_sequential_frames_and_publishes_silent_mp4(tmp_path):
    encoder = FakeEncoder()
    progress = []
    destination = tmp_path / "cinematic.mp4"
    coordinator = CinematicSkillRenderCoordinator(
        encoder=encoder,
        renderer_factory=lambda: FakeRenderer,
    )

    result = coordinator.render(
        FakeFilm(),
        destination,
        width=64,
        height=36,
        on_progress=lambda fraction, message: progress.append((fraction, message)),
    )

    assert result.destination == destination
    assert result.frame_count == 2
    assert result.fps == 10
    assert result.width == 64 and result.height == 36
    assert result.audio_included is False
    assert result.codec == "h264"
    assert result.output_sha256
    assert destination.read_bytes() == b"verified-by-fake-encoder"
    assert encoder.sequence.frame_count == 2
    assert encoder.sequence.fps == 10
    assert [path.name for path in encoder.sequence.frame_paths] == [
        "frame_000000.png", "frame_000001.png",
    ]
    assert progress[-1][0] == 1.0
    assert not list(tmp_path.glob(".voxora-cinematic-*"))


def test_cancellation_does_not_publish_or_leave_staging_files(tmp_path):
    coordinator = CinematicSkillRenderCoordinator(
        encoder=FakeEncoder(),
        renderer_factory=lambda: FakeRenderer,
    )
    with pytest.raises(CinematicSkillRenderCancelledError):
        coordinator.render(FakeFilm(), tmp_path / "cancelled.mp4", cancel=True)
    assert not (tmp_path / "cancelled.mp4").exists()
    assert not list(tmp_path.glob(".voxora-cinematic-*"))


def test_existing_destination_is_never_overwritten(tmp_path):
    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"keep")
    coordinator = CinematicSkillRenderCoordinator(
        encoder=FakeEncoder(),
        renderer_factory=lambda: FakeRenderer,
    )
    with pytest.raises(CinematicSkillRenderError, match="already exists"):
        coordinator.render(FakeFilm(), destination)
    assert destination.read_bytes() == b"keep"


def test_frame_and_resolution_budgets_are_enforced(tmp_path):
    coordinator = CinematicSkillRenderCoordinator(
        encoder=FakeEncoder(),
        renderer_factory=lambda: FakeRenderer,
        max_frames=1,
    )
    with pytest.raises(CinematicSkillRenderError, match="frame limit"):
        coordinator.render(FakeFilm(), tmp_path / "too-long.mp4")

    with pytest.raises(CinematicSkillRenderError, match="width"):
        coordinator.render(FakeFilm(), tmp_path / "too-wide.mp4", width=1921)


def test_missing_optional_runtime_is_reported_without_paid_fallback(tmp_path):
    def unavailable():
        raise CinematicSkillUnavailableError("optional local runtime missing")

    coordinator = CinematicSkillRenderCoordinator(
        encoder=FakeEncoder(),
        renderer_factory=unavailable,
    )
    with pytest.raises(CinematicSkillUnavailableError, match="optional local runtime"):
        coordinator.render(FakeFilm(), tmp_path / "unavailable.mp4")
