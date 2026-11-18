from __future__ import annotations

import copy

import pytest

from app.models.project import Project
from app.universal.profile_authoring import (
    apply_profiled_scene_plan_proposal,
    build_profiled_scene_plan_proposal,
)
from app.universal.profiles.models import ChannelProfile


def _profile(*, rules=None, presets=None):
    return ChannelProfile.from_dict({
        "schema_version": 1,
        "profile_id": "test-channel",
        "display_name": "Test Channel",
        "visual_defaults": {
            "style_family": "cinematic_sketch",
            "style_tags": ["sketch", "documentary"],
            "mood": ["curious"],
            "composition_guidance": ["Keep the frame readable."],
        },
        "rules": rules or [],
        "presets": presets or [],
    })


def test_profile_defaults_are_opt_in_and_do_not_change_ordinary_authoring():
    plain = build_profiled_scene_plan_proposal("A narration paragraph.")
    profiled = build_profiled_scene_plan_proposal(
        "A narration paragraph.", profile=_profile()
    )

    assert plain.profile_id is None
    assert plain.proposal.scenes[0].visual_plan.style_tags == []
    plan = profiled.proposal.scenes[0].visual_plan
    assert plan.style_tags == ["sketch", "documentary"]
    assert plan.requirements["profile_visual_defaults"] == {
        "style_family": "cinematic_sketch",
        "mood": ["curious"],
        "composition_guidance": ["Keep the frame readable."],
    }


def test_preset_visual_defaults_extend_profile_defaults_without_losing_them():
    profile = _profile(presets=[{
        "preset_id": "short_doc",
        "display_name": "Short Documentary",
        "visual_defaults": {
            "style_family": "paper_collage",
            "style_tags": ["paper_texture"],
            "mood": ["mysterious"],
            "composition_guidance": ["Use archival framing."],
        },
        "rules": [],
    }])
    result = build_profiled_scene_plan_proposal(
        "Narration.", profile=profile, selected_preset_id="short_doc"
    )
    plan = result.proposal.scenes[0].visual_plan
    assert plan.style_tags == ["sketch", "documentary", "paper_texture"]
    assert plan.requirements["profile_visual_defaults"] == {
        "style_family": "paper_collage",
        "mood": ["curious", "mysterious"],
        "composition_guidance": ["Keep the frame readable.", "Use archival framing."],
    }


def test_profile_rule_diagnostics_are_returned_and_block_apply_on_errors():
    profile = _profile(rules=[{
        "rule_id": "visual_prompt_required",
        "category": "required",
        "severity": "error",
        "scope": "scene",
        "target": "visual_prompt",
        "operator": "exists",
        "message": "Add a visual prompt before approval.",
    }])
    result = build_profiled_scene_plan_proposal("Narration.", profile=profile)
    assert not result.is_valid
    assert result.diagnostics[0].code == "PROFILE_RULE_REQUIRED"

    project = Project()
    before = copy.deepcopy(project)
    with pytest.raises(ValueError, match="Profile diagnostics"):
        apply_profiled_scene_plan_proposal(project, result)
    assert project == before


def test_warning_diagnostics_do_not_block_explicit_apply():
    profile = _profile(rules=[{
        "rule_id": "visual_prompt_recommended",
        "category": "recommended",
        "severity": "warning",
        "scope": "scene",
        "target": "visual_prompt",
        "operator": "exists",
        "message": "Consider adding a visual prompt.",
    }])
    result = build_profiled_scene_plan_proposal("Narration.", profile=profile)
    assert result.is_valid
    assert result.diagnostics[0].severity == "warning"

    project = Project()
    apply_profiled_scene_plan_proposal(project, result)
    assert len(project.scenes) == 1


def test_unknown_preset_is_reported_and_does_not_apply_profile_defaults():
    result = build_profiled_scene_plan_proposal(
        "Narration.", profile=_profile(), selected_preset_id="missing"
    )
    assert not result.is_valid
    assert result.diagnostics[0].code == "PROFILE_PRESET_NOT_FOUND"
    assert result.proposal.scenes[0].visual_plan.style_tags == []


def test_selected_preset_requires_explicit_profile():
    result = build_profiled_scene_plan_proposal(
        "Narration.", selected_preset_id="documentary"
    )
    assert not result.is_valid
    assert result.diagnostics[0].code == "PROFILE_REQUIRED"


def test_project_scope_rules_use_only_explicitly_supplied_context():
    profile = _profile(rules=[{
        "rule_id": "project_title_required",
        "category": "required",
        "severity": "error",
        "scope": "project",
        "target": "title",
        "operator": "exists",
        "message": "Project title is required.",
    }])
    missing = build_profiled_scene_plan_proposal(
        "Narration.", profile=profile, project_context={}
    )
    supplied = build_profiled_scene_plan_proposal(
        "Narration.", profile=profile, project_context={"title": "My Project"}
    )
    assert missing.diagnostics[0].code == "PROFILE_RULE_REQUIRED"
    assert supplied.diagnostics == ()

def test_apply_rechecks_profile_rules_after_a_proposal_is_edited():
    profile = _profile(rules=[{
        "rule_id": "avoid_disallowed_visual_prompt",
        "category": "required",
        "severity": "error",
        "scope": "scene",
        "target": "visual_prompt",
        "operator": "not_equals",
        "expected": "disallowed",
        "message": "Choose a different visual prompt.",
    }])
    result = build_profiled_scene_plan_proposal("Narration.", profile=profile)
    assert result.is_valid

    # A draft can be edited during review, so apply must not trust stale diagnostics.
    result.proposal.scenes[0].visual_prompt = "disallowed"
    assert not result.is_valid
    project = Project()
    before = copy.deepcopy(project)
    with pytest.raises(ValueError, match="Profile diagnostics"):
        apply_profiled_scene_plan_proposal(project, result)
    assert project == before

