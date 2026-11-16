from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.exceptions import MediaError
from app.universal.normalizer import (
    NormalizedSegment,
    SegmentNormalizer,
    SegmentOutputSpec,
)


class FakeFFmpeg:
    def __init__(self, info=None):
        self.info = info or SimpleNamespace(
            has_video=True, is_image=False, has_audio=False,
            width=640, height=360, duration_s=2.0,
        )
        self.calls = []
        self.probes = []

    def require(self):
        return Path("ffmpeg.exe")

    def run_with_progress(self, args, total_s, on_progress=None, cancel=None):
        self.calls.append((args, total_s, on_progress, cancel))
        Path(args[-1]).write_bytes(b"normalized video")

    def probe(self, path):
        self.probes.append(Path(path))
        return self.info


@pytest.mark.parametrize(
    "values",
    [
        (0, 640, 360, 30),
        (float("inf"), 640, 360, 30),
        (True, 640, 360, 30),
        (2.0, 0, 360, 30),
        (2.0, 640, -2, 30),
        (2.0, 640, 360, 0),
        (2.0, 641, 360, 30),
        (2.0, 640, 361, 30),
    ],
)
def test_output_spec_rejects_invalid_values(values):
    with pytest.raises(ValueError):
        SegmentOutputSpec(*values)


def test_normalizer_produces_and_verifies_shared_silent_mp4(tmp_path):
    source = tmp_path / "renderer-output.webm"
    source.write_bytes(b"raw")
    destination = tmp_path / "cache" / "scene.mp4"
    ffmpeg = FakeFFmpeg()
    normalizer = SegmentNormalizer(ffmpeg)
    progress = lambda value: value
    cancel = object()

    result = normalizer.normalize(
        source, destination, SegmentOutputSpec(2.0, 640, 360, 30),
        on_progress=progress, cancel=cancel,
    )

    assert isinstance(result, NormalizedSegment)
    assert result.path == destination
    assert result.container == "mp4"
    assert result.has_video is True
    assert result.has_audio is False
    assert (result.width, result.height, result.fps) == (640, 360, 30)
    assert result.duration_s == 2.0
    args, total_s, passed_progress, passed_cancel = ffmpeg.calls[0]
    assert args[args.index("-map") + 1] == "0:v:0"
    assert "-an" in args
    assert "fps=30" in args[args.index("-vf") + 1]
    assert "format=yuv420p" in args[args.index("-vf") + 1]
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-f") + 1] == "mp4"
    assert total_s == 2.0
    assert passed_progress is progress
    assert passed_cancel is cancel
    assert destination.read_bytes() == b"normalized video"
    assert not list(destination.parent.glob("*.part"))


@pytest.mark.parametrize(
    "info, message",
    [
        (SimpleNamespace(has_video=False, is_image=False, has_audio=False,
                         width=None, height=None, duration_s=2.0), "video stream"),
        (SimpleNamespace(has_video=True, is_image=False, has_audio=True,
                         width=640, height=360, duration_s=2.0), "audio stream"),
        (SimpleNamespace(has_video=True, is_image=False, has_audio=False,
                         width=1280, height=720, duration_s=2.0), "dimensions"),
        (SimpleNamespace(has_video=True, is_image=False, has_audio=False,
                         width=640, height=360, duration_s=5.0), "duration"),
        (SimpleNamespace(has_video=True, is_image=False, has_audio=False,
                         width=640, height=360, duration_s=None), "measurable duration"),
    ],
)
def test_normalizer_rejects_nonconforming_output_and_cleans_temp(tmp_path, info, message):
    source = tmp_path / "raw.mov"
    source.write_bytes(b"raw")
    destination = tmp_path / "scene.mp4"
    ffmpeg = FakeFFmpeg(info)
    with pytest.raises(MediaError, match=message):
        SegmentNormalizer(ffmpeg).normalize(
            source, destination, SegmentOutputSpec(2.0, 640, 360, 30)
        )
    assert not destination.exists()
    assert not list(tmp_path.glob("*.part"))


def test_normalizer_rejects_missing_source_and_same_source_destination(tmp_path):
    ffmpeg = FakeFFmpeg()
    normalizer = SegmentNormalizer(ffmpeg)
    spec = SegmentOutputSpec(2.0, 640, 360, 30)
    with pytest.raises(MediaError, match="missing or empty"):
        normalizer.normalize(tmp_path / "missing.mov", tmp_path / "out.mp4", spec)

    source = tmp_path / "same.mp4"
    source.write_bytes(b"raw")
    with pytest.raises(ValueError, match="different files"):
        normalizer.normalize(source, source, spec)


def test_normalizer_requires_mp4_destination(tmp_path):
    source = tmp_path / "raw.mov"
    source.write_bytes(b"raw")
    with pytest.raises(ValueError, match=r"\.mp4"):
        SegmentNormalizer(FakeFFmpeg()).normalize(
            source, tmp_path / "out.mkv", SegmentOutputSpec(2.0, 640, 360, 30)
        )


def test_normalizer_cleans_temporary_output_when_encoder_fails(tmp_path):
    class FailingFFmpeg(FakeFFmpeg):
        def run_with_progress(self, args, total_s, on_progress=None, cancel=None):
            Path(args[-1]).write_bytes(b"partial")
            raise RuntimeError("encoder failed")

    source = tmp_path / "raw.mov"
    source.write_bytes(b"raw")
    destination = tmp_path / "scene.mp4"
    with pytest.raises(RuntimeError, match="encoder failed"):
        SegmentNormalizer(FailingFFmpeg()).normalize(
            source, destination, SegmentOutputSpec(2.0, 640, 360, 30)
        )
    assert not destination.exists()
    assert not list(tmp_path.glob("*.part"))
