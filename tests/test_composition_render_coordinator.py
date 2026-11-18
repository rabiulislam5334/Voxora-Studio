from pathlib import Path

import pytest

from app.universal.composition_timeline import CompositionTimelinePlan
from app.universal.composition_render_coordinator import (
    CompositionRenderCoordinatorError,
    build_composition_concat_manifest,
    build_composition_silent_video_args,
)


def _plan(*, transition="cut", transition_ticks=0, frames=48):
    return CompositionTimelinePlan(
        project_id="project-a", fps=24, width=1280, height=720,
        transition=transition, transition_ticks=transition_ticks,
        total_ticks=2_000_000, total_frames=frames, slots=(),
        diagnostics=(), input_fingerprint="input", plan_fingerprint="plan",
    )


def test_concat_manifest_uses_one_still_per_scene_and_frame_based_durations(tmp_path: Path):
    first = tmp_path / "scene one.png"
    second = tmp_path / "scene_two.png"
    first.write_bytes(b"png")
    second.write_bytes(b"png")
    manifest = build_composition_concat_manifest(((first, 24), (second, 48)), 24)
    assert "file '" in manifest
    assert "duration 1.000000000000" in manifest
    assert "duration 2.000000000000" in manifest
    assert manifest.count("file ") == 3  # final file is repeated for concat duration semantics
    assert manifest.rstrip().endswith(str(second.resolve()).replace("\\", "/") + "'")


def test_concat_manifest_rejects_empty_and_invalid_frame_ranges(tmp_path: Path):
    frame = tmp_path / "scene.png"
    frame.write_bytes(b"png")
    with pytest.raises(CompositionRenderCoordinatorError, match="at least one"):
        build_composition_concat_manifest((), 24)
    with pytest.raises(CompositionRenderCoordinatorError, match="at least one frame"):
        build_composition_concat_manifest(((frame, 0),), 24)


def test_silent_video_command_encodes_exact_cfr_h264_frame_count(tmp_path: Path):
    args = build_composition_silent_video_args(
        Path("ffmpeg"), tmp_path / "frames.ffconcat", _plan(frames=73),
        tmp_path / "silent.mp4",
    )
    assert args[args.index("-f") + 1] == "concat"
    assert args[args.index("-r") + 1] == "24"
    assert args[args.index("-frames:v") + 1] == "73"
    assert args[args.index("-c:v") + 1] == "libx264"
    assert args[args.index("-an") + 1] == "-c:v"


def test_silent_video_command_rejects_crossfade_until_transition_renderer_exists(tmp_path: Path):
    with pytest.raises(CompositionRenderCoordinatorError, match="cut transitions"):
        build_composition_silent_video_args(
            Path("ffmpeg"), tmp_path / "frames.ffconcat",
            _plan(transition="crossfade", transition_ticks=500),
            tmp_path / "silent.mp4",
        )
