from __future__ import annotations

import pytest

from app.universal.production_director import (
    DirectorIntent,
    ProductionDirector,
    ProductionDirectorConfig,
    SceneRole,
)
from app.universal.profiles.models import ChannelProfile
from app.universal.storyboard import StoryboardValidationError, TimingBasis
from app.universal.narration_segmentation import segment_narration


def profile(profile_id="quasivanta", style="cinematic_scientific_visualization", tags=("infographics",)):
    return ChannelProfile.from_dict({
        "schema_version": 1,
        "profile_id": profile_id,
        "display_name": profile_id.title(),
        "visual_defaults": {
            "style_family": style,
            "style_tags": list(tags),
            "mood": ["curious"],
            "composition_guidance": ["Keep visual claims proportional to the narration."],
        },
    })


def test_director_creates_stable_profile_aware_scene_and_shot_plan():
    source = segment_narration(
        "Why does the planet move? Its orbit follows gravity.",
        source_id="script-01",
        total_duration_ms=8000,
    )
    director = ProductionDirector()
    first = director.create_plan(source, profile())
    second = director.create_plan(source, profile())

    assert first.to_dict() == second.to_dict()
    assert first.plan_id.startswith("director-")
    assert first.profile_id == "quasivanta"
    assert first.profile_style_family == "cinematic_scientific_visualization"
    assert len(first.shots) == len(source.units)
    assert first.shots[0].intent is DirectorIntent.QUESTION_REVEAL
    assert first.shots[1].intent is DirectorIntent.DIAGRAM
    assert all("cinematic_scientific_visualization" in shot.visual_prompt for shot in first.shots)
    assert all(shot.timing.basis is TimingBasis.ESTIMATED for shot in first.shots)
    assert first.requires_review is True


def test_director_preserves_measured_timing_and_narration_unit_mapping():
    from app.universal.storyboard import TimingInterval
    source = segment_narration(
        "The ship crossed the ocean. A letter described the route.",
        source_id="script-02",
        measured_timings={
            "unit-0001": TimingInterval(200, 1900, TimingBasis.MEASURED),
            "unit-0002": TimingInterval(2100, 4100, TimingBasis.MEASURED),
        },
    )
    plan = ProductionDirector().create_plan(source, profile("veltracis", "documentary_collage_2_5d"))
    assert [shot.timing for shot in plan.shots] == [unit.timing for unit in source.units]
    assert [shot.narration_unit_ids for shot in plan.shots] == [
        (unit.unit_id,) for unit in source.units
    ]
    assert plan.shots[0].intent is DirectorIntent.MAP
    assert plan.shots[1].intent is DirectorIntent.EVIDENCE


def test_scene_roles_follow_recovered_intro_outro_rule():
    source = segment_narration(
        "A question begins.\n\nA map shows the route.\n\nA document reveals the answer.",
        source_id="roles",
        total_duration_ms=9000,
    )
    plan = ProductionDirector().create_plan(source, profile("veltracis", "documentary_collage_2_5d"))
    assert len(plan.scenes) == 3
    assert [scene.role for scene in plan.scenes] == [
        SceneRole.INTRO, SceneRole.BODY, SceneRole.OUTRO
    ]

    two_scene_source = segment_narration(
        "A question begins.\n\nA map shows the route.",
        source_id="two-scenes",
        total_duration_ms=6000,
    )
    two_scene_plan = ProductionDirector().create_plan(
        two_scene_source, profile("veltracis", "documentary_collage_2_5d")
    )
    assert len(two_scene_plan.scenes) == 2
    assert all(scene.role is SceneRole.BODY for scene in two_scene_plan.scenes)


def test_director_applies_rihvaya_sensitive_visual_constraints():
    source = segment_narration(
        "The story describes a journey through the desert.",
        source_id="faith-story",
    )
    plan = ProductionDirector().create_plan(
        source, profile("rihvaya", "respectful_islamic_documentary")
    )
    prompt = plan.shots[0].visual_prompt
    assert "Never depict Prophets or Sahaba with identifiable facial features." in prompt
    assert "Do not invent religious dialogue" in prompt


def test_director_groups_shots_within_configured_bound():
    source = segment_narration(
        "A quiet forest appeared. Birds moved above the trees. The wind crossed the valley. A storm approached.",
        source_id="bounded",
        total_duration_ms=12000,
    )
    plan = ProductionDirector(ProductionDirectorConfig(max_shots_per_scene=2)).create_plan(
        source, profile("sizzjin", "cinematic_illustration_2_5d")
    )
    assert all(len(scene.shot_ids) <= 2 for scene in plan.scenes)


def test_director_rejects_empty_script_and_invalid_config():
    empty = segment_narration("", source_id="empty")
    with pytest.raises(StoryboardValidationError, match="non-empty script"):
        ProductionDirector().create_plan(empty, profile())
    with pytest.raises(StoryboardValidationError, match="from 1 to 12"):
        ProductionDirectorConfig(max_shots_per_scene=13)
