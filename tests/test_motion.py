import pytest

from app.universal.composition import (
    CompositionElement,
    SceneComposition,
)
from app.universal.motion import (
    MotionKeyframe,
    MotionTrack,
    MotionValidationError,
    SceneMotion,
    evaluate_scene_motion,
)


def _track(
    *, track_id="move-x", target_type="element", target_id="hero",
    property_name="x", keyframes=None,
):
    return MotionTrack(
        track_id=track_id,
        target_type=target_type,
        target_id=target_id,
        property_name=property_name,
        keyframes=tuple(keyframes or (
            MotionKeyframe(0, 0.0, "linear"),
            MotionKeyframe(10, 1.0),
        )),
    )


def test_linear_motion_evaluation_is_frame_deterministic():
    motion = SceneMotion("scene-a", 11, (_track(),))
    first = evaluate_scene_motion(motion, 0)
    middle = evaluate_scene_motion(motion, 5)
    last = evaluate_scene_motion(motion, 10)

    assert first.value_for("element", "hero", "x") == 0.0
    assert middle.value_for("element", "hero", "x") == 0.5
    assert last.value_for("element", "hero", "x") == 1.0


def test_easing_and_hold_interpolation_are_applied_from_left_keyframe():
    ease = SceneMotion("scene-a", 11, (_track(keyframes=(
        MotionKeyframe(0, 0.0, "ease_in"),
        MotionKeyframe(10, 1.0),
    )),))
    hold = SceneMotion("scene-a", 11, (_track(keyframes=(
        MotionKeyframe(0, 2.0, "hold"),
        MotionKeyframe(10, 8.0),
    )),))

    assert evaluate_scene_motion(ease, 5).values[0].value == 0.25
    assert evaluate_scene_motion(hold, 9).values[0].value == 2.0
    assert evaluate_scene_motion(hold, 10).values[0].value == 8.0


def test_motion_holds_first_and_last_values_outside_keyframe_range():
    motion = SceneMotion("scene-a", 20, (_track(keyframes=(
        MotionKeyframe(4, 3.0),
        MotionKeyframe(8, 7.0),
    )),))

    assert evaluate_scene_motion(motion, 0).values[0].value == 3.0
    assert evaluate_scene_motion(motion, 19).values[0].value == 7.0


def test_camera_tracks_are_supported_without_composition_elements():
    motion = SceneMotion("scene-a", 11, (
        _track(
            track_id="camera-zoom", target_type="camera", target_id="camera",
            property_name="zoom",
            keyframes=(MotionKeyframe(0, 1.0), MotionKeyframe(10, 2.0)),
        ),
    ))

    result = evaluate_scene_motion(motion, 5)
    assert result.value_for("camera", "camera", "zoom") == 1.5


def test_composition_validation_rejects_missing_element_targets():
    motion = SceneMotion("scene-a", 11, (_track(),))
    composition = SceneComposition(
        composition_id="comp-a",
        scene_id="scene-a",
        elements=(CompositionElement(element_id="background", asset_id="asset-a"),),
    )

    try:
        evaluate_scene_motion(motion, 5, composition=composition)
    except MotionValidationError as exc:
        assert "missing composition elements" in str(exc)
    else:
        raise AssertionError("missing motion target should be rejected")


def test_motion_rejects_duplicate_property_tracks_and_unsorted_keyframes():
    with pytest.raises(MotionValidationError, match="only have one"):
        SceneMotion("scene-a", 11, (_track(), _track(track_id="duplicate")))
    with __import__("pytest").raises(MotionValidationError, match="ordered by unique"):
        _track(keyframes=(MotionKeyframe(5, 0), MotionKeyframe(3, 1)))


def test_motion_rejects_invalid_frames_values_and_unknown_properties():
    with __import__("pytest").raises(MotionValidationError, match="non-negative"):
        MotionKeyframe(-1, 0)
    with __import__("pytest").raises(MotionValidationError, match="finite"):
        MotionKeyframe(0, float("nan"))
    with __import__("pytest").raises(MotionValidationError, match="unsupported"):
        _track(property_name="execute_python")
    with __import__("pytest").raises(MotionValidationError, match="inside the scene duration"):
        SceneMotion("scene-a", 10, (_track(),))


def test_scene_motion_round_trip_preserves_unknown_metadata():
    motion = SceneMotion(
        "scene-a", 11, (_track(),),
        extra={"future_motion_field": {"enabled": True}},
    )

    restored = SceneMotion.from_dict(motion.to_dict())
    assert restored.to_dict() == motion.to_dict()
    assert evaluate_scene_motion(restored, 5).values == evaluate_scene_motion(motion, 5).values


def test_evaluation_rejects_frame_outside_duration_and_wrong_scene():
    motion = SceneMotion("scene-a", 11, (_track(),))
    composition = SceneComposition(composition_id="comp-b", scene_id="scene-b")

    with __import__("pytest").raises(MotionValidationError, match="inside"):
        evaluate_scene_motion(motion, 11)
    with __import__("pytest").raises(MotionValidationError, match="scene IDs"):
        evaluate_scene_motion(motion, 0, composition=composition)
