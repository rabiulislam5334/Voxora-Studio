from __future__ import annotations

from copy import deepcopy

import pytest

from app.core.timebase import TICKS_PER_SECOND
from app.models.project import Project
from app.models.scene import Scene
from app.studio.models import SceneVideo, StudioState, VideoSettings
from app.universal.composition import CompositionElement, SceneComposition
from app.universal.composition_timeline import (
    CompositionTimelinePlanError,
    StaleCompositionTimelinePlanError,
    assert_composition_timeline_plan_current,
    build_composition_timeline_plan,
)
from app.universal.composition_workflow import (
    apply_scene_composition,
    preview_scene_composition,
)
from app.universal.models import AssetRef, ScenePlan, UniversalState


def _ticks(seconds: float) -> int:
    return round(seconds * TICKS_PER_SECOND)


def _project_with_compositions(*, transition: str = "crossfade") -> Project:
    project = Project(name="Timeline test", scenes=[
        Scene(id="scene-a", title="First", text="First narration", order=0, pause_ms=200),
        Scene(id="scene-b", title="Second", text="Second narration", order=1, pause_ms=100),
    ])
    state = UniversalState()
    state.scene_plans = {
        "scene-a": ScenePlan(
            scene_id="scene-a",
            asset_refs=[AssetRef("asset-a", "image", path="assets/a.png", identity="sha256-a")],
        ),
        "scene-b": ScenePlan(
            scene_id="scene-b",
            asset_refs=[AssetRef("asset-b", "image", path="assets/b.png", identity="sha256-b")],
        ),
    }
    project.settings = state.apply_to_project_settings(project.settings)
    for scene_id, asset_id in (("scene-a", "asset-a"), ("scene-b", "asset-b")):
        composition = SceneComposition(
            composition_id=f"composition-{scene_id}",
            scene_id=scene_id,
            elements=(CompositionElement(
                element_id=f"element-{scene_id}", asset_id=asset_id,
            ),),
        )
        preview = preview_scene_composition(project, composition)
        assert preview.is_valid
        apply_scene_composition(project, composition, preview, approved=True)
    studio = StudioState(video=VideoSettings(
        fps=24,
        transition=transition,
        transition_s=0.25,
        default_duration_s=3.0,
        scenes={"scene-a": SceneVideo(duration_s=2.0)},
    ))
    studio.write_to(project.settings)
    return project


def test_builds_deterministic_scene_slots_from_existing_timeline_contract():
    project = _project_with_compositions()
    before_settings = deepcopy(project.settings)
    before_scenes = deepcopy(project.scenes)
    narration = {"scene-a": _ticks(1.0), "scene-b": _ticks(3.5)}

    first = build_composition_timeline_plan(project, narration)
    second = build_composition_timeline_plan(project, narration)

    assert first == second
    assert first.is_valid
    assert first.requires_review is False
    assert [slot.scene_id for slot in first.slots] == ["scene-a", "scene-b"]
    assert first.total_ticks == _ticks(5.6)
    assert first.total_frames == 134
    assert first.transition == "crossfade"
    assert first.transition_ticks == _ticks(0.25)
    assert first.slots[0].start_ticks == 0
    assert first.slots[0].slot_ticks == _ticks(2.0)
    assert first.slots[0].segment_ticks == _ticks(2.25)
    assert first.slots[0].frame_start == 0
    assert first.slots[0].frame_end == 48
    assert first.slots[0].segment_frame_end == 54
    assert first.slots[1].start_ticks == _ticks(2.0)
    assert first.slots[1].slot_ticks == _ticks(3.6)
    assert first.slots[1].timing_basis == "measured_narration"
    assert first.slots[0].timing_basis == "configured_floor"
    assert first.slots[0].assets[0].identity == "sha256-a"
    assert first.slots[0].assets[0].path == "assets/a.png"
    assert project.settings == before_settings
    assert project.scenes == before_scenes


def test_uses_scene_pause_ms_when_explicit_pause_map_is_not_supplied():
    project = _project_with_compositions(transition="cut")
    plan = build_composition_timeline_plan(
        project, {"scene-a": _ticks(1.0), "scene-b": _ticks(1.0)}
    )
    assert plan.slots[0].pause_ticks == _ticks(0.2)
    assert plan.slots[1].pause_ticks == _ticks(0.1)
    assert plan.slots[0].slot_ticks == _ticks(2.0)
    assert plan.slots[1].slot_ticks == _ticks(1.5)


def test_explicit_pause_ticks_override_scene_pause_ms():
    project = _project_with_compositions(transition="cut")
    plan = build_composition_timeline_plan(
        project,
        {"scene-a": _ticks(1.0), "scene-b": _ticks(1.0)},
        narration_pause_ticks={"scene-a": _ticks(0.5), "scene-b": 0},
    )
    assert plan.slots[0].pause_ticks == _ticks(0.5)
    assert plan.slots[1].pause_ticks == 0


def test_missing_measured_narration_is_visible_as_review_diagnostic():
    project = _project_with_compositions(transition="cut")
    plan = build_composition_timeline_plan(project, {"scene-a": _ticks(1.0)})
    assert plan.is_valid
    assert plan.requires_review
    assert any(item.code == "NARRATION_TIMING_MISSING" and item.scene_id == "scene-b"
               for item in plan.diagnostics)
    assert plan.slots[1].timing_basis == "default_estimate"


def test_missing_scene_composition_blocks_render_plan():
    project = _project_with_compositions()
    state = UniversalState.from_project_settings(project.settings)
    stored = state.extra["scene_compositions"]
    stored.pop("scene-b")
    state.extra["scene_compositions"] = stored
    project.settings = state.apply_to_project_settings(project.settings)

    plan = build_composition_timeline_plan(
        project, {"scene-a": _ticks(1), "scene-b": _ticks(1)}
    )
    assert not plan.is_valid
    assert any(item.code == "SCENE_COMPOSITION_MISSING" and item.scene_id == "scene-b"
               for item in plan.diagnostics)


def test_rejects_unknown_or_invalid_timing_inputs():
    project = _project_with_compositions()
    with pytest.raises(CompositionTimelinePlanError, match="unknown scenes"):
        build_composition_timeline_plan(project, {"not-a-scene": 10})
    with pytest.raises(CompositionTimelinePlanError, match="non-negative integer"):
        build_composition_timeline_plan(project, {"scene-a": True})
    with pytest.raises(CompositionTimelinePlanError, match="non-negative integer"):
        build_composition_timeline_plan(project, {"scene-a": -1})


def test_rejects_read_only_universal_or_studio_settings():
    project = _project_with_compositions()
    project.settings["universal"] = {"format_version": 999, "scene_plans": {}}
    with pytest.raises(CompositionTimelinePlanError, match="Universal project data is read-only"):
        build_composition_timeline_plan(project, {})

    project = _project_with_compositions()
    project.settings["studio"] = {"version": 999}
    with pytest.raises(CompositionTimelinePlanError, match="Studio timeline settings"):
        build_composition_timeline_plan(project, {})


def test_stale_plan_detects_scene_composition_asset_and_timing_changes():
    project = _project_with_compositions()
    narration = {"scene-a": _ticks(1.0), "scene-b": _ticks(1.0)}
    plan = build_composition_timeline_plan(project, narration)
    assert_composition_timeline_plan_current(project, plan, narration)

    project.scenes[0].text = "Changed narration"
    with pytest.raises(StaleCompositionTimelinePlanError, match="stale"):
        assert_composition_timeline_plan_current(project, plan, narration)

    project = _project_with_compositions()
    plan = build_composition_timeline_plan(project, narration)
    assert_composition_timeline_plan_current(project, plan, narration)
    state = UniversalState.from_project_settings(project.settings)
    state.scene_plans["scene-a"].asset_refs[0].identity = "changed-sha"
    project.settings = state.apply_to_project_settings(project.settings)
    with pytest.raises(StaleCompositionTimelinePlanError, match="stale"):
        assert_composition_timeline_plan_current(project, plan, narration)

    project = _project_with_compositions()
    plan = build_composition_timeline_plan(project, narration)
    with pytest.raises(StaleCompositionTimelinePlanError, match="stale"):
        assert_composition_timeline_plan_current(
            project, plan, narration, narration_pause_ticks={"scene-a": _ticks(0.4)}
        )


def test_rejects_corrupt_persisted_composition_fingerprint():
    project = _project_with_compositions()
    state = UniversalState.from_project_settings(project.settings)
    state.extra["scene_compositions"]["scene-a"]["composition_fingerprint"] = "0" * 64
    project.settings = state.apply_to_project_settings(project.settings)
    with pytest.raises(CompositionTimelinePlanError, match="fingerprint is inconsistent"):
        build_composition_timeline_plan(project, {})


def test_cut_transition_has_no_overlap_segments():
    project = _project_with_compositions(transition="cut")
    plan = build_composition_timeline_plan(
        project, {"scene-a": _ticks(1.0), "scene-b": _ticks(1.0)}
    )
    assert plan.transition_ticks == 0
    assert plan.slots[0].segment_ticks == plan.slots[0].slot_ticks
    assert plan.slots[0].segment_end_ticks == plan.slots[0].end_ticks
