from __future__ import annotations

from pathlib import Path

from app.cache.video_cache import VideoCache
from app.core.timebase import frames_to_ticks, seconds_to_ticks
from app.video.render import (
    SegmentSpec,
    build_mux_args,
    build_segment_args,
    build_xfade_script_ticks,
)


def test_segment_spec_uses_explicit_frame_count_as_authority():
    spec = SegmentSpec(
        "blank", None, 1.001, 640, 360, 30,
        length_ticks=seconds_to_ticks("1.001"), frame_count=30,
    )
    assert spec.frames == 30


def test_segment_spec_derives_frame_count_from_canonical_ticks():
    duration_ticks = frames_to_ticks(45, 30)
    spec = SegmentSpec("blank", None, 1.5, 640, 360, 30, length_ticks=duration_ticks)
    assert spec.frames == 45


def test_segment_commands_are_limited_by_frame_count_not_rounded_seconds():
    spec = SegmentSpec(
        "blank", None, 1.234567, 640, 360, 30,
        length_ticks=seconds_to_ticks("1.234567"), frame_count=37,
    )
    args = build_segment_args(Path("ffmpeg"), spec, Path("out.mp4"))
    assert args[args.index("-frames:v") + 1] == "37"
    assert "-t" not in args


def test_crossfade_script_uses_frame_aligned_tick_boundaries():
    script = build_xfade_script_ticks(
        [frames_to_ticks(0, 30), frames_to_ticks(30, 30)],
        frames_to_ticks(15, 30),
    )
    assert "duration=0.5" in script
    assert "offset=1" in script


def test_mux_uses_exact_frame_duration_and_frame_limit():
    duration_ticks = frames_to_ticks(45, 30)
    args = build_mux_args(
        Path("ffmpeg"), Path("joined.mp4"), Path("audio.wav"),
        1.5, Path("out.mp4"), frame_count=45, duration_ticks=duration_ticks,
    )
    assert args[args.index("-t") + 1] == "1.5"
    assert args[args.index("-frames:v") + 1] == "45"
    assert "-shortest" in args


def test_video_cache_key_changes_when_authoritative_frame_count_changes(tmp_path):
    cache = VideoCache(tmp_path / "cache")
    first = SegmentSpec("blank", None, 1.0, 640, 360, 30, frame_count=30)
    second = SegmentSpec("blank", None, 1.0, 640, 360, 30, frame_count=31)
    assert cache.segment_key(first) != cache.segment_key(second)
