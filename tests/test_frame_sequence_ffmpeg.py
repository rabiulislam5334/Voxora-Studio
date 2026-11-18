from pathlib import Path
import shutil

import pytest
from PIL import Image

from app.universal.frame_sequence import (
    FFmpegFrameSequenceEncoder,
    FrameSequence,
    FrameSequenceCancelledError,
    FrameSequenceError,
    FrameSequenceLimits,
    build_frame_sequence_encode_args,
)


def _make_frames(folder: Path, *, count=3, size=(64, 48)):
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(count):
        path = folder / f"shot_{index:06d}.png"
        Image.new("RGBA", size, (index * 40, 20, 80, 255)).save(path)
        paths.append(path)
    return paths


def test_frame_sequence_accepts_contiguous_numbered_pngs(tmp_path):
    paths = _make_frames(tmp_path)
    sequence = FrameSequence.from_paths(paths, fps=24)
    assert sequence.frame_count == 3
    assert sequence.start_number == 0
    assert sequence.input_pattern.name == "shot_%06d.png"
    assert sequence.fps == 24


@pytest.mark.parametrize("names", [
    ["shot_000000.png", "shot_000002.png"],
    ["shot_000000.png", "other_000001.png"],
    ["shot_0000.png", "shot_00001.png"],
    ["frame_000000.jpg"],
    ["frame.png"],
])
def test_frame_sequence_rejects_non_contiguous_or_ambiguous_names(tmp_path, names):
    paths = [tmp_path / name for name in names]
    with pytest.raises(ValueError):
        FrameSequence.from_paths(paths, fps=24)


@pytest.mark.parametrize("fps", [0, 121, True, 24.0])
def test_frame_sequence_rejects_invalid_fps(tmp_path, fps):
    paths = _make_frames(tmp_path, count=1)
    with pytest.raises(ValueError, match="fps"):
        FrameSequence.from_paths(paths, fps=fps)


def test_encode_args_use_image_sequence_and_exact_frame_count(tmp_path):
    paths = _make_frames(tmp_path, count=4)
    sequence = FrameSequence.from_paths(paths, fps=30)
    args = build_frame_sequence_encode_args("ffmpeg", sequence, tmp_path / "out.mp4")
    assert args[args.index("-framerate") + 1] == "30"
    assert args[args.index("-start_number") + 1] == "0"
    assert args[args.index("-frames:v") + 1] == "4"
    assert args[args.index("-i") + 1].endswith("shot_%06d.png")
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert args[-1].endswith("out.mp4")


def test_inspection_rejects_different_frame_dimensions(tmp_path):
    paths = _make_frames(tmp_path, count=2)
    Image.new("RGB", (32, 32), "red").save(paths[1])
    encoder = FFmpegFrameSequenceEncoder()
    with pytest.raises(FrameSequenceError, match="identical dimensions"):
        encoder.encode(FrameSequence.from_paths(paths, fps=24), tmp_path / "out.mp4")


def test_inspection_rejects_odd_dimensions_for_yuv420p(tmp_path):
    paths = _make_frames(tmp_path, count=1, size=(63, 48))
    encoder = FFmpegFrameSequenceEncoder()
    with pytest.raises(FrameSequenceError, match="even frame dimensions"):
        encoder.encode(FrameSequence.from_paths(paths, fps=24), tmp_path / "out.mp4")


def test_inspection_rejects_non_png_content(tmp_path):
    path = tmp_path / "frame_000000.png"
    path.write_text("not an image", encoding="utf-8")
    encoder = FFmpegFrameSequenceEncoder()
    with pytest.raises(FrameSequenceError, match="cannot inspect|valid PNG"):
        encoder.encode(FrameSequence.from_paths([path], fps=24), tmp_path / "out.mp4")


def test_inspection_obeys_resource_limits(tmp_path):
    paths = _make_frames(tmp_path, count=2)
    encoder = FFmpegFrameSequenceEncoder(limits=FrameSequenceLimits(max_frames=1))
    with pytest.raises(FrameSequenceError, match="frame-count"):
        encoder.encode(FrameSequence.from_paths(paths, fps=24), tmp_path / "out.mp4")


def test_encoder_requires_mp4_and_explicit_overwrite(tmp_path):
    paths = _make_frames(tmp_path, count=1)
    sequence = FrameSequence.from_paths(paths, fps=24)
    encoder = FFmpegFrameSequenceEncoder()
    with pytest.raises(FrameSequenceError, match=".mp4"):
        encoder.encode(sequence, tmp_path / "out.mov")
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"keep")
    with pytest.raises(FrameSequenceError, match="explicit overwrite"):
        encoder.encode(sequence, existing)
    assert existing.read_bytes() == b"keep"


def test_encoder_rejects_pre_cancelled_job_without_output(tmp_path):
    paths = _make_frames(tmp_path, count=1)
    sequence = FrameSequence.from_paths(paths, fps=24)
    encoder = FFmpegFrameSequenceEncoder()
    destination = tmp_path / "cancelled.mp4"
    with pytest.raises(FrameSequenceCancelledError):
        encoder.encode(sequence, destination, cancel=True)
    assert not destination.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")
def test_ffmpeg_encoder_creates_verified_h264_mp4(tmp_path):
    paths = _make_frames(tmp_path, count=4, size=(64, 48))
    sequence = FrameSequence.from_paths(paths, fps=2)
    encoder = FFmpegFrameSequenceEncoder()
    progress = []
    destination = tmp_path / "encoded.mp4"

    result = encoder.encode(sequence, destination, on_progress=progress.append)

    assert result.destination == destination
    assert result.frame_count == 4
    assert result.fps == 2
    assert (result.width, result.height) == (64, 48)
    assert result.duration_seconds == 2.0
    assert len(result.output_sha256) == 64
    assert destination.is_file() and destination.stat().st_size > 0
    assert progress[0] == 0.0 and progress[-1] == 1.0

def test_frame_sequence_adapter_declares_cpu_mp4_encoding_contract():
    from app.universal.frame_sequence import (
        BUILTIN_FRAME_SEQUENCE_ENCODER_IDS,
        FFmpegFrameSequenceAdapter,
        build_builtin_frame_sequence_encoder,
    )

    class FakeEncoder:
        def encode(self, sequence, destination, **kwargs):
            return (sequence, destination, kwargs)

    adapter = FFmpegFrameSequenceAdapter(FakeEncoder())
    assert adapter.engine_id == "ffmpeg-frame-sequence"
    assert adapter.descriptor.capabilities.output_formats == ("mp4",)
    assert adapter.descriptor.capabilities.requires_gpu is False
    assert BUILTIN_FRAME_SEQUENCE_ENCODER_IDS == ("ffmpeg-frame-sequence",)
    registry = build_builtin_frame_sequence_encoder(FakeEncoder())
    assert tuple(registry) == BUILTIN_FRAME_SEQUENCE_ENCODER_IDS
    assert registry["ffmpeg-frame-sequence"].encoder.__class__ is FakeEncoder
