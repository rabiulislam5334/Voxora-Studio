import pytest

from app.universal.composition_timeline import (
    CompositionSceneSlot,
    CompositionTimelinePlan,
)
from app.universal.motion import MotionKeyframe, MotionTrack, SceneMotion
from app.universal.motion_timeline import (
    MotionTimelinePlanError,
    assert_motion_timeline_plan_current,
    build_motion_timeline_plan,
)


def _slot(scene_id, order, start, end, *, composition=True, segment_end=None):
    segment_end = end if segment_end is None else segment_end
    return CompositionSceneSlot(
        scene_id=scene_id,
        scene_order=order,
        composition_id=f"composition-{scene_id}" if composition else None,
        composition_fingerprint=f"composition-fingerprint-{scene_id}" if composition else None,
        composition_target_fingerprint=f"target-fingerprint-{scene_id}" if composition else None,
        assets=(),
        start_ticks=start,
        slot_ticks=end - start,
        segment_ticks=segment_end - start,
        end_ticks=end,
        segment_end_ticks=segment_end,
        frame_start=start,
        frame_end=end,
        segment_frame_end=segment_end,
        narration_duration_ticks=None,
        pause_ticks=0,
        timing_basis="configured",
        extended_for_narration=False,
    )


def _composition_plan(*, transition="cut", slots=None, total_frames=6):
    slots = slots if slots is not None else (
        _slot("scene-a", 0, 0, 3),
        _slot("scene-b", 1, 3, 6),
    )
    return CompositionTimelinePlan(
        project_id="project-motion",
        fps=3,
        width=32,
        height=18,
        transition=transition,
        transition_ticks=0 if transition == "cut" else 1,
        total_ticks=2_000_000,
        total_frames=total_frames,
        slots=tuple(slots),
        diagnostics=(),
        input_fingerprint="input-fingerprint",
        plan_fingerprint="composition-plan-fingerprint",
    )


def _motion(scene_id, duration=3, *, x_end=0.8):
    track = MotionTrack(
        track_id=f"{scene_id}-x",
        target_type="element",
        target_id="subject",
        property_name="x",
        keyframes=(
            MotionKeyframe(frame=0, value=0.1),
            MotionKeyframe(frame=duration - 1, value=x_end),
        ),
    )
    return SceneMotion(scene_id=scene_id, duration_frames=duration, tracks=(track,))


def test_motion_timeline_plan_binds_exact_scene_frame_ranges_deterministically():
    composition = _composition_plan()
    motions = {
        "scene-b": _motion("scene-b"),
        "scene-a": _motion("scene-a"),
    }

    plan = build_motion_timeline_plan(composition, motions)

    assert [item.scene_id for item in plan.scenes] == ["scene-a", "scene-b"]
    assert [(item.frame_start, item.frame_end, item.segment_frame_end) for item in plan.scenes] == [
        (0, 3, 3), (3, 6, 6),
    ]
    assert plan.total_frames == 6
    assert plan.fps == 3
    assert len(plan.motion_fingerprint) == 64
    assert plan.transition == "cut"
    assert plan.transition_frames == 0
    assert len(plan.plan_fingerprint) == 64
    assert build_motion_timeline_plan(composition, motions) == plan


def test_motion_timeline_plan_allows_explicit_static_scene_motion():
    composition = _composition_plan()
    motions = {
        "scene-a": SceneMotion(scene_id="scene-a", duration_frames=3),
        "scene-b": SceneMotion(scene_id="scene-b", duration_frames=3),
    }

    plan = build_motion_timeline_plan(composition, motions)

    assert len(plan.scenes) == 2
    assert all(not item.motion.tracks for item in plan.scenes)


def test_motion_timeline_plan_rejects_missing_and_unknown_scene_motion():
    composition = _composition_plan()

    with pytest.raises(MotionTimelinePlanError, match="missing motion"):
        build_motion_timeline_plan(composition, {"scene-a": _motion("scene-a")})

    with pytest.raises(MotionTimelinePlanError, match="unknown scenes"):
        build_motion_timeline_plan(composition, {
            "scene-a": _motion("scene-a"),
            "scene-b": _motion("scene-b"),
            "scene-c": _motion("scene-c"),
        })


def test_motion_timeline_plan_rejects_duration_mismatch_and_wrong_scene_id():
    composition = _composition_plan()

    with pytest.raises(MotionTimelinePlanError, match="requires exactly"):
        build_motion_timeline_plan(composition, {
            "scene-a": _motion("scene-a", duration=2),
            "scene-b": _motion("scene-b"),
        })

    with pytest.raises(MotionTimelinePlanError, match="does not match"):
        build_motion_timeline_plan(composition, {
            "scene-a": _motion("scene-x"),
            "scene-b": _motion("scene-b"),
        })


def test_motion_timeline_plan_binds_crossfade_overlap_frames():
    composition = _composition_plan(
        transition="crossfade",
        slots=(
            _slot("scene-a", 0, 0, 3, segment_end=4),
            _slot("scene-b", 1, 3, 6),
        ),
    )
    motions = {
        "scene-a": _motion("scene-a", duration=4),
        "scene-b": _motion("scene-b", duration=3),
    }

    plan = build_motion_timeline_plan(composition, motions)

    assert plan.transition == "crossfade"
    assert plan.transition_frames == 1
    assert [(item.frame_start, item.frame_end, item.segment_frame_end) for item in plan.scenes] == [
        (0, 3, 4), (3, 6, 6),
    ]
    assert [item.frame_count for item in plan.scenes] == [4, 3]


def test_motion_timeline_plan_rejects_crossfade_motion_without_overlap_frames():
    composition = _composition_plan(transition="crossfade")
    with pytest.raises(MotionTimelinePlanError, match="shorter than one output frame"):
        build_motion_timeline_plan(
            composition,
            {"scene-a": _motion("scene-a"), "scene-b": _motion("scene-b")},
        )


def test_motion_timeline_plan_rejects_crossfade_with_single_scene():
    composition = _composition_plan(
        transition="crossfade",
        slots=(_slot("scene-a", 0, 0, 3),),
        total_frames=3,
    )
    with pytest.raises(MotionTimelinePlanError, match="at least two scenes"):
        build_motion_timeline_plan(composition, {"scene-a": _motion("scene-a")})


def test_motion_timeline_plan_rejects_gaps_and_missing_compositions():
    with pytest.raises(MotionTimelinePlanError, match="contiguous"):
        build_motion_timeline_plan(
            _composition_plan(slots=(
                _slot("scene-a", 0, 0, 2),
                _slot("scene-b", 1, 3, 6),
            )),
            {"scene-a": _motion("scene-a", duration=2), "scene-b": _motion("scene-b")},
        )

    with pytest.raises(MotionTimelinePlanError, match="no validated composition"):
        build_motion_timeline_plan(
            _composition_plan(slots=(
                _slot("scene-a", 0, 0, 3, composition=False),
                _slot("scene-b", 1, 3, 6),
            )),
            {"scene-a": _motion("scene-a"), "scene-b": _motion("scene-b")},
        )


def test_motion_timeline_plan_detects_changed_motion_inputs():
    composition = _composition_plan()
    original = {
        "scene-a": _motion("scene-a"),
        "scene-b": _motion("scene-b"),
    }
    plan = build_motion_timeline_plan(composition, original)

    changed = {
        "scene-a": _motion("scene-a", x_end=0.9),
        "scene-b": _motion("scene-b"),
    }
    with pytest.raises(MotionTimelinePlanError, match="stale"):
        assert_motion_timeline_plan_current(composition, changed, plan)


def test_motion_timeline_plan_rejects_incomplete_total_frame_coverage():
    with pytest.raises(MotionTimelinePlanError, match="do not cover"):
        build_motion_timeline_plan(
            _composition_plan(total_frames=7),
            {"scene-a": _motion("scene-a"), "scene-b": _motion("scene-b")},
        )
