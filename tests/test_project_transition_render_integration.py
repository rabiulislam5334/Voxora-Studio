from types import SimpleNamespace

import pytest

from app.core.timebase import seconds_to_ticks
from app.studio.models import STUDIO_SETTINGS_KEY, StudioState, VideoSettings
from app.universal.composition_timeline import CompositionSceneSlot, CompositionTimelinePlan
from app.universal.motion import SceneMotion
from app.universal.motion_timeline import (
    MotionTimelinePlanError,
    assert_project_transition_settings_current,
    build_project_motion_timeline_plan,
    resolve_project_transition_specs,
)
from app.universal.transitions import TransitionSpec


def _composition_plan():
    overlap_ticks = seconds_to_ticks(0.5)
    return CompositionTimelinePlan(
        project_id="project-transition-integration",
        fps=3,
        width=32,
        height=18,
        transition="crossfade",
        transition_ticks=overlap_ticks,
        total_ticks=seconds_to_ticks(2),
        total_frames=6,
        slots=(
            CompositionSceneSlot(
                scene_id="scene-a", scene_order=0,
                composition_id="composition-a",
                composition_fingerprint="fingerprint-a",
                composition_target_fingerprint="target-a",
                assets=(), start_ticks=0, slot_ticks=seconds_to_ticks(1),
                segment_ticks=seconds_to_ticks(1.5), end_ticks=seconds_to_ticks(1),
                segment_end_ticks=seconds_to_ticks(1.5),
                frame_start=0, frame_end=3, segment_frame_end=4,
                narration_duration_ticks=None, pause_ticks=0,
                timing_basis="configured", extended_for_narration=False,
            ),
            CompositionSceneSlot(
                scene_id="scene-b", scene_order=1,
                composition_id="composition-b",
                composition_fingerprint="fingerprint-b",
                composition_target_fingerprint="target-b",
                assets=(), start_ticks=seconds_to_ticks(1),
                slot_ticks=seconds_to_ticks(1), segment_ticks=seconds_to_ticks(1),
                end_ticks=seconds_to_ticks(2), segment_end_ticks=seconds_to_ticks(2),
                frame_start=3, frame_end=6, segment_frame_end=6,
                narration_duration_ticks=None, pause_ticks=0,
                timing_basis="configured", extended_for_narration=False,
            ),
        ),
        diagnostics=(),
        input_fingerprint="input-fingerprint",
        plan_fingerprint="composition-plan-fingerprint",
    )


def _project(effect="wipe_left", *, duration_ticks=None):
    spec = TransitionSpec(
        effect=effect,
        duration_ticks=duration_ticks or seconds_to_ticks(0.5),
        easing="ease_in_out",
        color_rgb=(12, 34, 56) if effect == "dip_to_color" else None,
    )
    studio = StudioState(video=VideoSettings(
        transition="crossfade",
        transition_s=0.5,
        extra={
            "scene_transitions": {
                "version": 1,
                "scenes": {"scene-a": spec.to_dict()},
            }
        },
    ))
    settings = {}
    studio.write_to(settings)
    return SimpleNamespace(settings=settings)


def _motions():
    return {
        "scene-a": SceneMotion(scene_id="scene-a", duration_frames=4),
        "scene-b": SceneMotion(scene_id="scene-b", duration_frames=3),
    }


def test_saved_transition_editor_effect_is_bound_to_render_plan():
    project = _project("wipe_left")
    plan = build_project_motion_timeline_plan(project, _composition_plan(), _motions())

    assert dict(plan.transition_specs)["scene-a"].effect == "wipe_left"
    assert dict(plan.transition_specs)["scene-a"].easing == "ease_in_out"


def test_saved_dip_color_is_preserved_for_the_renderer():
    project = _project("dip_to_color")
    specs = resolve_project_transition_specs(project, _composition_plan())

    assert specs["scene-a"].effect == "dip_to_color"
    assert specs["scene-a"].color_rgb == (12, 34, 56)


def test_saved_transition_duration_must_match_approved_overlap():
    project = _project("wipe_left", duration_ticks=seconds_to_ticks(0.4))

    with pytest.raises(MotionTimelinePlanError, match="does not match"):
        build_project_motion_timeline_plan(project, _composition_plan(), _motions())


def test_saved_transition_cannot_reference_a_scene_without_an_outgoing_boundary():
    project = _project()
    project.settings[STUDIO_SETTINGS_KEY]["video"]["scene_transitions"]["scenes"]["scene-b"] = (
        TransitionSpec(effect="wipe_right", duration_ticks=seconds_to_ticks(0.5)).to_dict()
    )

    with pytest.raises(MotionTimelinePlanError, match="without outgoing boundaries"):
        resolve_project_transition_specs(project, _composition_plan())


def test_render_plan_is_rejected_when_saved_transition_changes_after_approval():
    project = _project("wipe_left")
    composition = _composition_plan()
    plan = build_project_motion_timeline_plan(project, composition, _motions())

    project.settings[STUDIO_SETTINGS_KEY]["video"]["scene_transitions"]["scenes"]["scene-a"] = (
        TransitionSpec(
            effect="wipe_right",
            duration_ticks=seconds_to_ticks(0.5),
            easing="ease_in_out",
        ).to_dict()
    )

    with pytest.raises(MotionTimelinePlanError, match="changed after timeline approval"):
        assert_project_transition_settings_current(project, composition, _motions(), plan)


def test_missing_scene_overrides_keep_the_default_crossfade_behavior():
    project = _project()
    project.settings[STUDIO_SETTINGS_KEY]["video"]["scene_transitions"]["scenes"] = {}
    plan = build_project_motion_timeline_plan(project, _composition_plan(), _motions())

    assert dict(plan.transition_specs)["scene-a"].effect == "crossfade"
