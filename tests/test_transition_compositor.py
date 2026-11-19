import shutil

import pytest
from PIL import Image

from app.universal.frame_sequence import FFmpegFrameSequenceEncoder, FrameSequence
from app.universal.transition_compositor import (
    TransitionCompositorError,
    composite_transition_frames,
)
from app.universal.transitions import TransitionSpec


def _frames():
    return (
        Image.new("RGBA", (4, 4), (255, 0, 0, 255)),
        Image.new("RGBA", (4, 4), (0, 0, 255, 255)),
    )


@pytest.mark.parametrize(
    "effect, expected_incoming",
    [
        ("wipe_left", (0, 0)),
        ("wipe_right", (3, 0)),
        ("wipe_up", (0, 0)),
        ("wipe_down", (0, 3)),
    ],
)
def test_directional_wipes_reveal_from_the_named_edge(effect, expected_incoming):
    outgoing, incoming = _frames()
    try:
        spec = TransitionSpec(effect=effect, duration_ticks=10)
        first = composite_transition_frames(outgoing, incoming, spec, 0, 5)
        middle = composite_transition_frames(outgoing, incoming, spec, 2, 5)
        last = composite_transition_frames(outgoing, incoming, spec, 4, 5)
        assert first.getpixel(expected_incoming) == (255, 0, 0, 255)
        assert last.getpixel(expected_incoming) == (0, 0, 255, 255)
        assert middle.size == outgoing.size
        first.close()
        middle.close()
        last.close()
    finally:
        outgoing.close()
        incoming.close()


def test_wipes_assign_every_pixel_and_preserve_exact_endpoints():
    outgoing, incoming = _frames()
    try:
        for effect in ("wipe_left", "wipe_right", "wipe_up", "wipe_down"):
            spec = TransitionSpec(effect=effect, duration_ticks=10)
            first = composite_transition_frames(outgoing, incoming, spec, 0, 7)
            last = composite_transition_frames(outgoing, incoming, spec, 6, 7)
            assert list(first.getdata()) == list(outgoing.getdata())
            assert list(last.getdata()) == list(incoming.getdata())
            first.close()
            last.close()
    finally:
        outgoing.close()
        incoming.close()


def test_crossfade_uses_eased_progress_and_exact_endpoints():
    outgoing, incoming = _frames()
    try:
        spec = TransitionSpec(effect="crossfade", duration_ticks=10, easing="ease_in")
        first = composite_transition_frames(outgoing, incoming, spec, 0, 3)
        middle = composite_transition_frames(outgoing, incoming, spec, 1, 3)
        last = composite_transition_frames(outgoing, incoming, spec, 2, 3)
        assert first.getpixel((0, 0)) == (255, 0, 0, 255)
        assert middle.getpixel((0, 0)) == (191, 0, 64, 255)
        assert last.getpixel((0, 0)) == (0, 0, 255, 255)
        first.close()
        middle.close()
        last.close()
    finally:
        outgoing.close()
        incoming.close()


@pytest.mark.parametrize("frame_count", [5, 6])
def test_dip_to_color_has_deterministic_odd_and_even_midpoint(frame_count):
    outgoing, incoming = _frames()
    try:
        color = (12, 34, 56)
        spec = TransitionSpec(
            effect="dip_to_color", duration_ticks=10, color_rgb=color,
        )
        frames = [
            composite_transition_frames(outgoing, incoming, spec, index, frame_count)
            for index in range(frame_count)
        ]
        assert frames[0].getpixel((0, 0)) == (255, 0, 0, 255)
        assert frames[-1].getpixel((0, 0)) == (0, 0, 255, 255)
        if frame_count % 2:
            assert frames[frame_count // 2].getpixel((0, 0)) == (*color, 255)
        else:
            assert frames[frame_count // 2 - 1].getpixel((0, 0)) != (*color, 255)
            assert frames[frame_count // 2].getpixel((0, 0)) != (*color, 255)
        for frame in frames:
            frame.close()
    finally:
        outgoing.close()
        incoming.close()


def test_compositor_rejects_mismatched_frames_and_cut():
    outgoing, incoming = _frames()
    wrong_size = Image.new("RGBA", (2, 2), (0, 0, 0, 255))
    wrong_mode = Image.new("RGB", (4, 4), (0, 0, 0))
    try:
        spec = TransitionSpec(effect="crossfade", duration_ticks=10)
        with pytest.raises(TransitionCompositorError, match="dimensions"):
            composite_transition_frames(outgoing, wrong_size, spec, 0, 2)
        with pytest.raises(TransitionCompositorError, match="modes"):
            composite_transition_frames(outgoing, wrong_mode, spec, 0, 2)
        with pytest.raises(TransitionCompositorError, match="cut"):
            composite_transition_frames(
                outgoing, incoming, TransitionSpec.cut(), 0, 2,
            )
    finally:
        outgoing.close()
        incoming.close()
        wrong_size.close()
        wrong_mode.close()


@pytest.mark.parametrize("effect", ["wipe_left", "dip_to_color"])
def test_advanced_transition_frames_encode_to_verified_mp4(tmp_path, effect):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and FFprobe are required for this integration test")
    outgoing, incoming = _frames()
    paths = []
    try:
        spec = (TransitionSpec(effect="dip_to_color", duration_ticks=10, color_rgb=(8, 16, 24))
                if effect == "dip_to_color" else TransitionSpec(effect=effect, duration_ticks=10))
        for index in range(5):
            frame = composite_transition_frames(outgoing, incoming, spec, index, 5)
            path = tmp_path / f"frame_{index:06d}.png"
            frame.save(path, format="PNG")
            frame.close()
            paths.append(path)
    finally:
        outgoing.close()
        incoming.close()

    sequence = FrameSequence.from_paths(paths, fps=5)
    result = FFmpegFrameSequenceEncoder(
        ffmpeg_executable=ffmpeg, ffprobe_executable=ffprobe,
    ).encode(sequence, tmp_path / "advanced-transition.mp4")

    assert result.frame_count == 5
    assert result.fps == 5
    assert result.width == 4 and result.height == 4
    assert result.codec == "h264"
    assert result.duration_seconds == pytest.approx(1.0)


def test_single_frame_overlap_preserves_legacy_midpoint_crossfade():
    outgoing, incoming = _frames()
    try:
        spec = TransitionSpec(effect="crossfade", duration_ticks=1)
        result = composite_transition_frames(outgoing, incoming, spec, 0, 1)
        assert result.getpixel((0, 0)) == (128, 0, 128, 255)
        result.close()
    finally:
        outgoing.close()
        incoming.close()
