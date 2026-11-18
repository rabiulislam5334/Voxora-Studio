from pathlib import Path

import pytest
from PIL import Image

from app.universal.composition import (
    CompositionCanvas, CompositionElement, SceneComposition, VisualTransform,
)
from app.universal.motion import MotionKeyframe, MotionTrack, SceneMotion
from app.universal.motion_raster_renderer import (
    MotionRasterRenderCancelledError,
    MotionRasterRenderError,
    MotionRasterRenderer,
)


def _composition(*, width=16, height=16, x=0.0, y=0.0, box_width=1.0,
                 box_height=1.0, opacity=1.0):
    return SceneComposition(
        composition_id="composition-a",
        scene_id="scene-a",
        canvas=CompositionCanvas(width, height),
        elements=(
            CompositionElement(
                element_id="hero",
                asset_id="hero-asset",
                transform=VisualTransform(
                    x=x, y=y, width=box_width, height=box_height, opacity=opacity,
                ),
                fit_mode="stretch",
            ),
        ),
    )


def _motion(*tracks, duration=11):
    return SceneMotion("scene-a", duration, tuple(tracks))


def _track(property_name, start, end, *, target_type="element", target_id="hero"):
    return MotionTrack(
        track_id=f"{target_type}-{property_name}",
        target_type=target_type,
        target_id=target_id,
        property_name=property_name,
        keyframes=(
            MotionKeyframe(0, start, "linear"),
            MotionKeyframe(10, end),
        ),
    )


def _save(path: Path, color=(255, 0, 0, 255), size=(4, 4)):
    Image.new("RGBA", size, color).save(path)
    return path


def _pixel(path, point):
    with Image.open(path) as image:
        return image.convert("RGBA").getpixel(point)


def test_motion_values_change_real_element_pixels_at_selected_frames(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition(box_width=0.25, box_height=0.25)
    motion = _motion(_track("x", 0.0, 0.5))
    renderer = MotionRasterRenderer()

    first = renderer.render_frame(
        composition, motion, 0,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "frame-000.png",
    )
    last = renderer.render_frame(
        composition, motion, 10,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "frame-010.png",
    )

    assert first.frame == 0 and last.frame == 10
    assert _pixel(first.destination, (1, 1)) == (255, 0, 0, 255)
    assert _pixel(last.destination, (1, 1))[3] == 0
    assert _pixel(last.destination, (9, 1)) == (255, 0, 0, 255)


def test_motion_opacity_is_applied_to_rendered_pixels(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition()
    motion = _motion(_track("opacity", 1.0, 0.0))

    result = MotionRasterRenderer().render_frame(
        composition, motion, 5,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "half-opacity.png",
    )

    assert _pixel(result.destination, (8, 8))[3] in (127, 128)


def test_camera_pan_moves_the_rendered_canvas_and_exposes_transparency(tmp_path):
    source = _save(tmp_path / "background.png", (0, 180, 20, 255), size=(16, 16))
    composition = _composition()
    motion = _motion(_track(
        "pan_x", 0.0, 0.25, target_type="camera", target_id="camera",
    ))

    result = MotionRasterRenderer().render_frame(
        composition, motion, 10,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "camera-pan.png",
    )

    assert _pixel(result.destination, (0, 8))[3] == 0
    assert _pixel(result.destination, (5, 8)) == (0, 180, 20, 255)


def test_camera_zoom_is_applied_around_canvas_center(tmp_path):
    source = _save(tmp_path / "background.png", (20, 40, 220, 255), size=(16, 16))
    composition = _composition()
    motion = _motion(_track(
        "zoom", 1.0, 2.0, target_type="camera", target_id="camera",
    ))

    result = MotionRasterRenderer().render_frame(
        composition, motion, 10,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "camera-zoom.png",
    )

    assert _pixel(result.destination, (8, 8)) == (20, 40, 220, 255)
    assert _pixel(result.destination, (0, 0))[3] == 0


def test_camera_rotation_is_applied_to_final_composition(tmp_path):
    source = _save(tmp_path / "wide.png", (200, 30, 30, 255), size=(16, 4))
    composition = _composition(box_width=1.0, box_height=0.25)
    motion = _motion(_track(
        "rotation_degrees", 0.0, 90.0, target_type="camera", target_id="camera",
    ))

    result = MotionRasterRenderer().render_frame(
        composition, motion, 10,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "camera-rotation.png",
    )

    with Image.open(result.destination) as image:
        alpha = image.getchannel("A")
        bbox = alpha.getbbox()
        assert bbox is not None
        assert bbox[3] - bbox[1] > bbox[2] - bbox[0]


def test_sequence_renders_all_frames_and_publishes_numbered_pngs(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition(box_width=0.25, box_height=0.25)
    motion = _motion(_track("x", 0.0, 0.5), duration=3)
    progress = []

    result = MotionRasterRenderer().render_sequence(
        composition, motion,
        asset_paths={"hero-asset": source},
        destination_dir=tmp_path / "sequence",
        on_progress=lambda fraction, message: progress.append((fraction, message)),
    )

    assert result.frame_count == 3
    assert [path.name for path in result.frame_paths] == [
        "frame_000000.png", "frame_000001.png", "frame_000002.png",
    ]
    assert all(path.is_file() for path in result.frame_paths)
    assert progress[-1][0] == 1.0


def test_cancelled_sequence_removes_staging_directory(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition()
    motion = _motion(duration=3)

    with pytest.raises(MotionRasterRenderCancelledError):
        MotionRasterRenderer().render_sequence(
            composition, motion,
            asset_paths={"hero-asset": source},
            destination_dir=tmp_path / "cancelled-sequence",
            cancel=True,
        )

    assert not (tmp_path / "cancelled-sequence").exists()
    assert not list(tmp_path.glob(".voxora-motion-sequence-*"))


def test_sequence_frame_limit_and_existing_destination_are_enforced(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition()
    motion = _motion(duration=3)
    renderer = MotionRasterRenderer(max_sequence_frames=2)

    with pytest.raises(MotionRasterRenderError, match="frame limit"):
        renderer.render_sequence(
            composition, motion,
            asset_paths={"hero-asset": source},
            destination_dir=tmp_path / "too-many",
        )

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(MotionRasterRenderError, match="already exists"):
        MotionRasterRenderer().render_sequence(
            composition, motion,
            asset_paths={"hero-asset": source},
            destination_dir=existing,
        )


def test_wrong_scene_and_invalid_frame_are_rejected(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition()
    motion = SceneMotion("another-scene", 11, ())

    with pytest.raises(MotionRasterRenderError, match="scene IDs"):
        MotionRasterRenderer().render_frame(
            composition, motion, 0,
            asset_paths={"hero-asset": source},
            destination=tmp_path / "wrong-scene.png",
        )

    matching = _motion(duration=3)
    with pytest.raises(MotionRasterRenderError, match="Invalid scene motion"):
        MotionRasterRenderer().render_frame(
            composition, matching, 3,
            asset_paths={"hero-asset": source},
            destination=tmp_path / "invalid-frame.png",
        )


def test_rendering_does_not_mutate_source_composition_or_motion(tmp_path):
    source = _save(tmp_path / "hero.png")
    composition = _composition(box_width=0.25, box_height=0.25)
    motion = _motion(_track("x", 0.0, 0.5))
    composition_before = composition.to_dict()
    motion_before = motion.to_dict()

    MotionRasterRenderer().render_frame(
        composition, motion, 10,
        asset_paths={"hero-asset": source},
        destination=tmp_path / "immutable.png",
    )

    assert composition.to_dict() == composition_before
    assert motion.to_dict() == motion_before
