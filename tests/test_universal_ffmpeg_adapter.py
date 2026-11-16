from pathlib import Path

import pytest

from app.universal.adapters.ffmpeg import FFmpegSegmentAdapter
from app.universal.engines import (
    EngineCompatibilityError,
    EngineRegistry,
)
from app.video.render import SegmentSpec, build_segment_args


class FakeFFmpeg:
    def __init__(self):
        self.calls = []

    def require(self):
        return Path("ffmpeg.exe")

    def run_with_progress(self, args, total_s, on_progress=None, cancel=None):
        self.calls.append((args, total_s, on_progress, cancel))


def test_adapter_exposes_explicit_ffmpeg_capabilities():
    adapter = FFmpegSegmentAdapter(FakeFFmpeg())

    assert adapter.descriptor.engine_id == "ffmpeg"
    assert adapter.descriptor.capabilities.scene_kinds == ("blank", "image", "video")
    assert adapter.descriptor.capabilities.asset_kinds == ("image", "video")
    assert adapter.descriptor.capabilities.output_formats == ("mp4",)
    assert adapter.descriptor.capabilities.requires_gpu is False
    assert adapter.descriptor.capabilities.supports_draft_render is True


@pytest.mark.parametrize(
    "spec",
    [
        SegmentSpec("blank", None, 2.0, 640, 360, 30),
        SegmentSpec("image", "scene.png", 2.0, 640, 360, 30, "zoom_in", "fill"),
        SegmentSpec("video", "clip.mp4", 2.0, 640, 360, 30, "none", "fit"),
    ],
)
def test_adapter_delegates_to_existing_segment_argument_builder(spec, tmp_path):
    ffmpeg = FakeFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)
    destination = tmp_path / "segment.part"

    result = adapter.render_segment(spec, destination)

    assert result == destination
    assert len(ffmpeg.calls) == 1
    args, total_s, progress, cancel = ffmpeg.calls[0]
    assert args == build_segment_args(Path("ffmpeg.exe"), spec, destination)
    assert total_s == spec.length_s
    assert progress is None
    assert cancel is None


def test_adapter_passes_progress_and_cancel_through_unchanged(tmp_path):
    ffmpeg = FakeFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)
    progress = lambda value: value
    cancel = object()
    spec = SegmentSpec("blank", None, 1.0, 320, 180, 15)

    adapter.render_segment(spec, tmp_path / "segment.mp4", on_progress=progress, cancel=cancel)

    assert ffmpeg.calls[0][2] is progress
    assert ffmpeg.calls[0][3] is cancel


@pytest.mark.parametrize(
    "spec",
    [
        SegmentSpec("unknown", None, 1.0, 320, 180, 15),
        SegmentSpec("image", None, 1.0, 320, 180, 15),
        SegmentSpec("video", "", 1.0, 320, 180, 15),
        SegmentSpec("blank", "unexpected.png", 1.0, 320, 180, 15),
        SegmentSpec("blank", None, 0.0, 320, 180, 15),
        SegmentSpec("blank", None, float("inf"), 320, 180, 15),
        SegmentSpec("blank", None, 10**1000, 320, 180, 15),
        SegmentSpec("blank", None, 1.0, 0, 180, 15),
        SegmentSpec("blank", None, 1.0, 320, 180, 0),
        SegmentSpec("image", "scene.png", 1.0, 320, 180, 15, "rotate", "fill"),
        SegmentSpec("image", "scene.png", 1.0, 320, 180, 15, "none", "stretch"),
    ],
)
def test_adapter_rejects_invalid_specs_without_running_ffmpeg(spec, tmp_path):
    ffmpeg = FakeFFmpeg()
    adapter = FFmpegSegmentAdapter(ffmpeg)

    with pytest.raises((TypeError, ValueError)):
        adapter.render_segment(spec, tmp_path / "bad.mp4")

    assert ffmpeg.calls == []


def test_registry_resolves_only_declared_ffmpeg_scene_capabilities():
    adapter = FFmpegSegmentAdapter(FakeFFmpeg())
    registry = EngineRegistry((adapter.descriptor,))

    assert registry.resolve(
        "ffmpeg", scene_kind="image", asset_kinds=("image",), output_format="mp4"
    ) is adapter.descriptor

    with pytest.raises(EngineCompatibilityError):
        registry.resolve("ffmpeg", scene_kind="3d_scene", output_format="mp4")
