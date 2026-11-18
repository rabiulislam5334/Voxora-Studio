from __future__ import annotations

from copy import deepcopy

import pytest

from app.models.project import Project
from app.models.scene import Scene
from app.universal.models import UniversalState
from app.universal.narration_segmentation import segment_narration
from app.universal.storyboard import StoryboardValidationError
from app.universal.storyboard_apply import (
    apply_storyboard_proposal,
    preview_storyboard_apply,
)
from app.universal.storyboard_builder import build_storyboard_proposal


def make_source_and_proposal():
    source = segment_narration(
        "The door opens. A shadow crosses the hall.",
        source_id="apply-source",
        total_duration_ms=4200,
    )
    proposal = build_storyboard_proposal(source)
    return source, proposal


def test_preview_is_deterministic_and_does_not_mutate_project():
    source, proposal = make_source_and_proposal()
    project = Project(name="Preview target", scenes=[
        Scene(id="existing-1", title="Existing", text="Keep this scene.")
    ])
    before_scenes = deepcopy(project.scenes)
    before_settings = deepcopy(project.settings)
    first = preview_storyboard_apply(project, proposal, source)
    second = preview_storyboard_apply(project, proposal, source)
    assert first == second
    assert first.is_valid
    assert len(first.scenes) == len(source.units)
    assert project.scenes == before_scenes
    assert project.settings == before_settings
    assert first.scenes[0].narration_text == source.text_for_unit(source.units[0])


def test_preview_exposes_visual_intent_and_timing_provenance():
    source, proposal = make_source_and_proposal()
    project = Project()
    preview = preview_storyboard_apply(project, proposal, source)
    assert preview.scenes[0].visual_prompt == proposal.beats[0].visual_description
    assert preview.scenes[0].start_ms == proposal.beats[0].timing.start_ms
    assert preview.scenes[0].end_ms == proposal.beats[0].timing.end_ms
    assert preview.scenes[0].timing_basis == proposal.beats[0].timing.basis.value


def test_apply_requires_explicit_approval_and_valid_preview():
    source, proposal = make_source_and_proposal()
    project = Project()
    preview = preview_storyboard_apply(project, proposal, source)
    with pytest.raises(StoryboardValidationError, match="explicit approval"):
        apply_storyboard_proposal(project, proposal, source, preview)
    assert project.scenes == []


def test_apply_adds_scenes_and_universal_plans_without_changing_existing_scenes():
    source, proposal = make_source_and_proposal()
    existing = Scene(id="keep-me", title="Keep", text="Existing narration", notes="Keep notes")
    project = Project(scenes=[existing])
    preview = preview_storyboard_apply(project, proposal, source)
    apply_storyboard_proposal(project, proposal, source, preview, approved=True)

    assert project.scenes[0].id == "keep-me"
    assert project.scenes[0].text == "Existing narration"
    created = project.scenes[1:]
    assert len(created) == len(proposal.beats)
    assert [scene.text for scene in created] == [
        source.text_for_unit(source.units[0]),
        source.text_for_unit(source.units[1]),
    ]
    state = UniversalState.from_project_settings(project.settings)
    assert not state.read_only
    assert set(state.scene_plans) == {scene.id for scene in created}
    assert all(state.scene_plans[scene.id].plan_status == "approved" for scene in created)
    assert proposal.proposal_id in state.extra["storyboard_applied_proposal_ids"]


def test_apply_is_idempotent_and_second_preview_reports_already_applied():
    source, proposal = make_source_and_proposal()
    project = Project()
    preview = preview_storyboard_apply(project, proposal, source)
    apply_storyboard_proposal(project, proposal, source, preview, approved=True)
    scene_count = len(project.scenes)
    repeated_preview = preview_storyboard_apply(project, proposal, source)
    assert not repeated_preview.is_valid
    assert any(item.code == "PROPOSAL_ALREADY_APPLIED" for item in repeated_preview.diagnostics)
    with pytest.raises(StoryboardValidationError, match="blocking diagnostics"):
        apply_storyboard_proposal(
            project, proposal, source, repeated_preview, approved=True
        )
    assert len(project.scenes) == scene_count


def test_apply_rejects_stale_source_and_stale_project_preview():
    source, proposal = make_source_and_proposal()
    project = Project()
    preview = preview_storyboard_apply(project, proposal, source)
    changed_source = segment_narration(
        "The door closes.", source_id=source.source_id, total_duration_ms=1200
    )
    with pytest.raises(StoryboardValidationError, match="blocking diagnostics|stale"):
        apply_storyboard_proposal(
            project, proposal, changed_source, preview, approved=True
        )

    source2, proposal2 = make_source_and_proposal()
    project2 = Project()
    preview2 = preview_storyboard_apply(project2, proposal2, source2)
    project2.scenes.append(Scene(id="new-scene", title="Concurrent edit"))
    with pytest.raises(StoryboardValidationError, match="stale"):
        apply_storyboard_proposal(
            project2, proposal2, source2, preview2, approved=True
        )


def test_preview_blocks_future_read_only_universal_state():
    source, proposal = make_source_and_proposal()
    project = Project(settings={"universal": {"format_version": 999, "opaque": True}})
    preview = preview_storyboard_apply(project, proposal, source)
    assert not preview.is_valid
    assert any(item.code == "UNIVERSAL_STATE_READ_ONLY" for item in preview.diagnostics)
    with pytest.raises(StoryboardValidationError, match="blocking diagnostics"):
        apply_storyboard_proposal(project, proposal, source, preview, approved=True)


def test_apply_preserves_unrelated_universal_data():
    source, proposal = make_source_and_proposal()
    project = Project(settings={"universal": {
        "format_version": 1,
        "profile_id": "quasivanta",
        "custom_extension": {"keep": [1, 2, 3]},
        "scene_plans": {},
    }})
    preview = preview_storyboard_apply(project, proposal, source)
    apply_storyboard_proposal(project, proposal, source, preview, approved=True)
    state = UniversalState.from_project_settings(project.settings)
    assert state.extra["custom_extension"] == {"keep": [1, 2, 3]}
    assert state.profile_id == "quasivanta"


def test_preview_flags_empty_proposal_as_not_applicable():
    source = segment_narration("", source_id="empty")
    proposal = build_storyboard_proposal(source)
    preview = preview_storyboard_apply(Project(), proposal, source)
    assert not preview.is_valid
    assert any(item.code == "EMPTY_STORYBOARD" for item in preview.diagnostics)
