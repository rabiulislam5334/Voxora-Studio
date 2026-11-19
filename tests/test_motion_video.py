from pathlib import Path
import shutil

import pytest
from PIL import Image

from app.universal.composition import (
    CompositionCanvas,
    CompositionElement,
    SceneComposition,
    VisualTransform,
)
from app.universal.motion import SceneMotion
from app.universal.motion_video import (
    MotionVideoRenderCancelledError,
    MotionVideoRenderCoordinator,
    MotionVideoRenderError,
)
from app.universal.frame_sequence import FFmpegFrameSequenceEncoder
from app.workers.cancel import CancelToken


def _inputs(tmp_path: Path, *, width=16, height=16):
    source = tmp_path / "source.png"
    Image.new("RGBA", (width, height), (30, 100, 220, 255)).save(source)
    composition = SceneComposition(
        composition_id="composition-motion-video",
        scene_id="scene-motion-video",
        canvas=CompositionCanvas(width, height),
        elements=(
            CompositionElement(
                element_id="background",
                asset_id="background-asset",
                transform=VisualTransform(x=0, y=0, width=1, height=1),
                fit_mode="stretch",
            ),
        ),
    )
    motion = SceneMotion(
        scene_id="scene-motion-video",
        duration_frames=3,
        tracks=(),
    )
    return composition, motion, {"background-asset": source}


def test_motion_video_coordinator_renders_and_verifies_real_mp4(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is not installed")
    ffprobe = shutil.which("ffprobe")
    composition, motion, assets = _inputs(tmp_path)
    progress = []
    coordinator = MotionVideoRenderCoordinator(
        encoder=FFmpegFrameSequenceEncoder(
            ffmpeg_executable=ffmpeg,
            ffprobe_executable=ffprobe,
        )
    )

    result = coordinator.run(
        composition,
        motion,
        asset_paths=assets,
        destination=tmp_path / "motion-output.mp4",
        fps=3,
        on_progress=lambda fraction, message: progress.append((fraction, message)),
    )

    assert result.destination.is_file()
    assert result.frame_count == 3
    assert result.fps == 3
    assert result.width == 16 and result.height == 16
    assert result.duration_seconds == pytest.approx(1.0)
    assert result.codec == "h264"
    assert len(result.output_sha256) == 64
    assert progress[-1][0] == 1.0
    assert not list(tmp_path.glob(".voxora-motion-video-*"))


def test_motion_video_coordinator_rejects_existing_output_before_render(tmp_path):
    composition, motion, assets = _inputs(tmp_path)
    destination = tmp_path / "existing.mp4"
    destination.write_bytes(b"keep")

    with pytest.raises(MotionVideoRenderError, match="already exists"):
        MotionVideoRenderCoordinator().run(
            composition,
            motion,
            asset_paths=assets,
            destination=destination,
            fps=24,
        )

    assert destination.read_bytes() == b"keep"


def test_motion_video_coordinator_honors_cancel_token_before_work(tmp_path):
    composition, motion, assets = _inputs(tmp_path)
    cancel = CancelToken()
    cancel.cancel()
    destination = tmp_path / "cancelled.mp4"

    with pytest.raises(MotionVideoRenderCancelledError):
        MotionVideoRenderCoordinator().run(
            composition,
            motion,
            asset_paths=assets,
            destination=destination,
            fps=24,
            cancel=cancel,
        )

    assert not destination.exists()
    assert not list(tmp_path.glob(".voxora-motion-video-*"))


def test_motion_video_coordinator_validates_frame_rate_and_destination(tmp_path):
    composition, motion, assets = _inputs(tmp_path)
    coordinator = MotionVideoRenderCoordinator()

    with pytest.raises(MotionVideoRenderError, match="fps"):
        coordinator.run(
            composition,
            motion,
            asset_paths=assets,
            destination=tmp_path / "bad.mp4",
            fps=0,
        )

    with pytest.raises(MotionVideoRenderError, match="extension"):
        coordinator.run(
            composition,
            motion,
            asset_paths=assets,
            destination=tmp_path / "bad.mov",
            fps=24,
        )
