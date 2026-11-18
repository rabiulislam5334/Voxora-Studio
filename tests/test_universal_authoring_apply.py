from __future__ import annotations

import copy
import hashlib

import pytest

from app.models.project import Project
from app.models.scene import Scene
from app.projects.manager import ProjectManager
from app.universal.authoring import (
    SceneAuthoringOptions,
    apply_scene_plan_proposal,
    build_scene_plan_proposal,
)
from app.universal.models import UniversalState


def test_apply_appends_scenes_and_approved_plans_without_touching_legacy_settings():
    project = Project(settings={"studio": {"volume": 72}, "other": {"keep": True}})
    before_settings = copy.deepcopy(project.settings)
    proposal = build_scene_plan_proposal(
        "First narration paragraph.\n\nSecond narration paragraph."
    )

    apply_scene_plan_proposal(project, proposal)

    assert [scene.text for scene in project.scenes] == [
        "First narration paragraph.", "Second narration paragraph."
    ]
    assert [scene.order for scene in project.scenes] == [0, 1]
    state = UniversalState.from_project_settings(project.settings)
    assert set(state.scene_plans) == {scene.id for scene in project.scenes}
    assert all(plan.plan_status == "approved" for plan in state.scene_plans.values())
    assert all(plan.engine_choice.engine_id is None for plan in state.scene_plans.values())
    assert all(plan.asset_refs == [] for plan in state.scene_plans.values())
    assert project.settings["studio"] == before_settings["studio"]
    assert project.settings["other"] == before_settings["other"]
    assert project.schema_version == 4


def test_apply_is_atomic_when_a_scene_id_collides_with_existing_project_scene():
    project = Project(scenes=[Scene(id="collision", text="Existing")])
    proposal = build_scene_plan_proposal("New narration")
    proposal.scenes[0].scene_id = "collision"
    proposal.scenes[0].visual_plan.scene_id = "collision"
    before = copy.deepcopy(project)

    with pytest.raises(ValueError, match="already exist"):
        apply_scene_plan_proposal(project, proposal)

    assert project == before


def test_apply_rejects_reapplying_the_same_proposal_without_duplicate_scenes():
    project = Project()
    proposal = build_scene_plan_proposal("A scene to apply.")
    apply_scene_plan_proposal(project, proposal)
    before = copy.deepcopy(project)

    with pytest.raises(ValueError, match="already been applied"):
        apply_scene_plan_proposal(project, proposal)

    assert project == before
    assert len(project.scenes) == 1


def test_existing_scenes_apply_edits_and_order_but_preserves_other_scene_fields():
    first = Scene(id="first", title="Opening", text="Opening narration", notes="old note",
                  visual_prompt="old visual", voice_id="en-US-BrianNeural")
    second = Scene(id="second", title="Ending", text="Ending narration")
    project = Project(scenes=[first, second], settings={"studio": {"theme": "dark"}})
    proposal = build_scene_plan_proposal(
        options=SceneAuthoringOptions(split_strategy="existing_scenes"),
        existing_scenes=project.scenes,
    )
    proposal.scenes[0].title = "Revised ending"
    proposal.scenes[0].text = "Revised ending narration"
    proposal.scenes[1].order = 0
    proposal.scenes[0].order = 1

    apply_scene_plan_proposal(project, proposal)

    assert [scene.id for scene in project.scenes] == ["second", "first"]
    assert project.scenes[1].title == "Revised ending"
    assert project.scenes[1].text == "Revised ending narration"
    assert project.scenes[1].voice_id == "en-US-BrianNeural"
    assert project.settings["studio"] == {"theme": "dark"}
    state = UniversalState.from_project_settings(project.settings)
    assert set(state.scene_plans) == {"first", "second"}


def test_existing_scene_proposal_rejects_stale_project_without_partial_mutation():
    project = Project(scenes=[Scene(id="one", title="One", text="Original")])
    proposal = build_scene_plan_proposal(
        options=SceneAuthoringOptions(split_strategy="existing_scenes"),
        existing_scenes=project.scenes,
    )
    project.scenes[0].text = "Changed elsewhere"
    before = copy.deepcopy(project)

    with pytest.raises(ValueError, match="changed after"):
        apply_scene_plan_proposal(project, proposal)

    assert project == before


def test_future_or_malformed_universal_payload_is_never_overwritten():
    project = Project(settings={
        "studio": {"keep": True},
        "universal": {"format_version": 99, "future_data": {"keep": [1, 2]}},
    })
    proposal = build_scene_plan_proposal("Narration")
    before = copy.deepcopy(project)

    with pytest.raises(ValueError, match="read-only"):
        apply_scene_plan_proposal(project, proposal)

    assert project == before


def test_invalid_plan_reference_fails_before_any_project_mutation():
    project = Project()
    proposal = build_scene_plan_proposal("Narration")
    proposal.scenes[0].visual_plan.scene_id = "not-the-scene-id"
    before = copy.deepcopy(project)

    with pytest.raises(ValueError, match="does not match"):
        apply_scene_plan_proposal(project, proposal)

    assert project == before


def test_applied_proposal_and_scene_plans_survive_voxora_save_and_reopen(tmp_path):
    manager = ProjectManager()
    manager.current_project = Project(
        name="Universal authoring round trip",
        settings={"studio": {"volume": 64}, "custom": {"preserve": "yes"}},
    )
    proposal = build_scene_plan_proposal(
        "প্রথম দৃশ্যের বর্ণনা।\n\nদ্বিতীয় দৃশ্যের বর্ণনা।"
    )

    apply_scene_plan_proposal(manager.current_project, proposal)
    manager.mark_dirty()
    path = manager.save(tmp_path / "universal-authoring.voxora")

    reopened = ProjectManager()
    reopened.open(path)

    assert reopened.current_project.schema_version == 4
    assert [scene.text for scene in reopened.current_project.scenes] == [
        "প্রথম দৃশ্যের বর্ণনা।", "দ্বিতীয় দৃশ্যের বর্ণনা।"
    ]
    assert reopened.current_project.settings["studio"] == {"volume": 64}
    assert reopened.current_project.settings["custom"] == {"preserve": "yes"}
    state = UniversalState.from_project_settings(reopened.current_project.settings)
    assert set(state.scene_plans) == {scene.id for scene in reopened.current_project.scenes}
    assert all(plan.plan_status == "approved" for plan in state.scene_plans.values())
    assert proposal.proposal_id in state.extra["authoring_applied_proposal_ids"]
    for scene in reopened.current_project.scenes:
        plan = state.scene_plans[scene.id]
        assert plan.script_hash == hashlib.sha256(scene.text.encode("utf-8")).hexdigest()

    with pytest.raises(ValueError, match="already been applied"):
        apply_scene_plan_proposal(reopened.current_project, proposal)
    assert len(reopened.current_project.scenes) == 2
