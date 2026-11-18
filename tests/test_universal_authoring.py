from __future__ import annotations

from copy import deepcopy

import pytest

from app.core.timebase import TICKS_PER_SECOND
from app.models.scene import Scene
from app.universal.authoring import (
    SceneAuthoringOptions,
    build_scene_plan_proposal,
)


def test_paragraph_split_is_ordered_and_creates_proposed_plans():
    proposal = build_scene_plan_proposal(
        "First scene has four.\n\nSecond scene has three.",
        options=SceneAuthoringOptions(words_per_minute=60),
    )
    assert proposal.is_valid
    assert [item.text for item in proposal.scenes] == [
        "First scene has four.", "Second scene has three."
    ]
    assert [item.order for item in proposal.scenes] == [0, 1]
    assert all(item.visual_plan.plan_status == "proposed" for item in proposal.scenes)
    assert all(item.visual_plan.kind == "unspecified" for item in proposal.scenes)
    assert all(item.visual_plan.engine_choice.engine_id is None for item in proposal.scenes)
    assert all(item.visual_plan.asset_refs == [] for item in proposal.scenes)


def test_duration_estimate_uses_canonical_ticks_and_is_not_audio_duration():
    proposal = build_scene_plan_proposal(
        "one two three four",
        options=SceneAuthoringOptions(split_strategy="manual", words_per_minute=60),
    )
    assert proposal.scenes[0].estimated_duration_ticks == 4 * TICKS_PER_SECOND
    assert proposal.scenes[0].word_count == 4


def test_explicit_marker_split_and_empty_segments_are_reported():
    proposal = build_scene_plan_proposal(
        "alpha<SCENE> <SCENE>beta",
        options=SceneAuthoringOptions(split_strategy="explicit_marker", explicit_marker="<SCENE>"),
    )
    assert [item.text for item in proposal.scenes] == ["alpha", "beta"]
    assert any(item.code == "empty_segment" and item.severity == "warning" for item in proposal.diagnostics)
    assert proposal.is_valid


def test_manual_strategy_keeps_entire_script_as_one_scene():
    script = "Line one.\n\nLine two."
    proposal = build_scene_plan_proposal(
        script, options=SceneAuthoringOptions(split_strategy="manual")
    )
    assert len(proposal.scenes) == 1
    assert proposal.scenes[0].text == script


def test_existing_scene_strategy_preserves_scene_ids_and_metadata():
    source = [
        Scene(id="scene-a", title="Opening", text="Narration A", notes="note", visual_prompt="wide shot"),
        Scene(id="scene-b", title="Ending", text="Narration B"),
    ]
    original = deepcopy(source)
    proposal = build_scene_plan_proposal(
        options=SceneAuthoringOptions(split_strategy="existing_scenes"),
        existing_scenes=source,
    )
    assert proposal.is_valid
    assert [item.scene_id for item in proposal.scenes] == ["scene-a", "scene-b"]
    assert proposal.scenes[0].notes == "note"
    assert proposal.scenes[0].visual_prompt == "wide shot"
    assert source == original


def test_duplicate_existing_scene_ids_are_rejected_without_misaligned_plans():
    source = [
        Scene(id="same", text="first"),
        Scene(id="same", text="second"),
    ]
    proposal = build_scene_plan_proposal(
        options=SceneAuthoringOptions(split_strategy="existing_scenes"),
        existing_scenes=source,
    )
    assert not proposal.is_valid
    assert len(proposal.scenes) == 0
    assert any(item.code == "duplicate_scene_id" for item in proposal.diagnostics)


@pytest.mark.parametrize("script", ["", "   ", "\n\n"])
def test_empty_script_produces_diagnostic_not_scene(script):
    proposal = build_scene_plan_proposal(script)
    assert not proposal.is_valid
    assert proposal.scenes == []
    assert any(item.code == "empty_script" for item in proposal.diagnostics)


def test_invalid_options_are_reported():
    proposal = build_scene_plan_proposal(
        "text", options=SceneAuthoringOptions(words_per_minute=0)
    )
    assert not proposal.is_valid
    assert proposal.scenes == []
    assert any(item.code == "invalid_options" for item in proposal.diagnostics)


def test_proposal_ids_are_stable_while_proposal_is_reviewed_and_new_between_builds():
    first = build_scene_plan_proposal("one paragraph")
    ids_before = [scene.scene_id for scene in first.scenes]
    ids_after = [scene.scene_id for scene in first.scenes]
    second = build_scene_plan_proposal("one paragraph")
    assert ids_before == ids_after
    assert ids_before != [scene.scene_id for scene in second.scenes]


def test_source_fingerprint_is_deterministic_and_independent_of_generated_ids():
    first = build_scene_plan_proposal("alpha\n\nbeta")
    second = build_scene_plan_proposal("alpha\n\nbeta")
    assert first.source_fingerprint == second.source_fingerprint


def test_bengali_script_word_count_uses_shared_word_counter():
    proposal = build_scene_plan_proposal(
        "একটি বাক্য।\n\nআরেকটি বাক্য।",
        options=SceneAuthoringOptions(words_per_minute=60),
    )
    assert [scene.word_count for scene in proposal.scenes] == [2, 2]


def test_wrong_input_type_is_reported():
    proposal = build_scene_plan_proposal(42)  # type: ignore[arg-type]
    assert not proposal.is_valid
    assert proposal.scenes == []
    assert any(item.code == "invalid_script" for item in proposal.diagnostics)


def test_empty_existing_scene_collection_is_rejected():
    proposal = build_scene_plan_proposal(
        options=SceneAuthoringOptions(split_strategy="existing_scenes"),
        existing_scenes=[],
    )
    assert not proposal.is_valid
    assert proposal.scenes == []
    assert any(item.code == "no_scenes" for item in proposal.diagnostics)
