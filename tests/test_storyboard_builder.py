from __future__ import annotations

import pytest

from app.universal.narration_segmentation import segment_narration
from app.universal.storyboard import (
    ContinuityKind,
    ContinuityReference,
    NarrationSource,
    NarrationTextUnit,
    ProposalReviewStatus,
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)
from app.universal.storyboard_builder import (
    StoryboardBuilderConfig,
    build_storyboard_proposal,
)


def source_with_units():
    return segment_narration(
        "The door opens. A shadow crosses the hall.",
        source_id="narration-01",
        total_duration_ms=4200,
    )


def test_builder_creates_one_stable_beat_per_narration_unit():
    source = source_with_units()
    first = build_storyboard_proposal(source)
    second = build_storyboard_proposal(source)
    assert first.to_dict() == second.to_dict()
    assert first.review_status is ProposalReviewStatus.NEEDS_REVIEW
    assert len(first.beats) == len(source.units)
    assert [beat.narration_unit_ids for beat in first.beats] == [
        (unit.unit_id,) for unit in source.units
    ]
    assert sum(beat.timing.duration_ms for beat in first.beats) == 4200
    assert all(beat.timing.basis is TimingBasis.ESTIMATED for beat in first.beats)


def test_builder_preserves_measured_unit_timing_and_provenance():
    source = NarrationSource(
        "s", "One. Two.",
        (
            NarrationTextUnit("u1", 0, 4, TimingInterval(100, 800, TimingBasis.MEASURED)),
            NarrationTextUnit("u2", 4, 9, TimingInterval(800, 1500, TimingBasis.MEASURED)),
        ),
        total_duration_ms=1500,
    )
    proposal = build_storyboard_proposal(source)
    assert [beat.timing for beat in proposal.beats] == [
        source.units[0].timing, source.units[1].timing
    ]


def test_builder_uses_configured_estimate_when_no_duration_or_timing_exists():
    source = segment_narration("One. Two.", source_id="s")
    proposal = build_storyboard_proposal(
        source, config=StoryboardBuilderConfig(default_beat_duration_ms=2300)
    )
    assert [(beat.timing.start_ms, beat.timing.end_ms) for beat in proposal.beats] == [
        (0, 2300), (2300, 4600)
    ]
    assert all(beat.timing.basis is TimingBasis.ESTIMATED for beat in proposal.beats)


def test_builder_uses_caller_authored_visual_intent_actions_and_refs():
    source = segment_narration("The door opens.", source_id="s")
    character = ContinuityReference("shadow", ContinuityKind.CHARACTER, "A distant silhouette")
    proposal = build_storyboard_proposal(
        source,
        visual_descriptions={"unit-0001": "A locked camera frames the old wooden door."},
        action_cues={"unit-0001": ("door handle turns", "door slowly opens")},
        continuity_references=(character,),
        continuity_reference_ids={"unit-0001": ("shadow",)},
    )
    beat = proposal.beats[0]
    assert beat.visual_description.startswith("A locked camera")
    assert beat.action_cues == ("door handle turns", "door slowly opens")
    assert beat.continuity_reference_ids == ("shadow",)


def test_builder_rejects_unknown_unit_or_unresolved_reference_inputs():
    source = source_with_units()
    with pytest.raises(StoryboardValidationError, match="unknown narration unit"):
        build_storyboard_proposal(source, visual_descriptions={"missing": "Visual"})
    with pytest.raises(StoryboardValidationError, match="unresolved reference"):
        build_storyboard_proposal(
            source, continuity_reference_ids={"unit-0001": ("missing",)}
        )


def test_builder_rejects_invalid_config_and_empty_descriptions():
    source = source_with_units()
    with pytest.raises(StoryboardValidationError, match="positive integer"):
        StoryboardBuilderConfig(default_beat_duration_ms=0)
    with pytest.raises(StoryboardValidationError, match="non-empty"):
        build_storyboard_proposal(source, visual_descriptions={"unit-0001": " "})


def test_builder_preserves_gaps_in_measured_timing():
    source = NarrationSource(
        "s", "One. Two.",
        (
            NarrationTextUnit("u1", 0, 4, TimingInterval(0, 500, TimingBasis.MEASURED)),
            NarrationTextUnit("u2", 4, 9, TimingInterval(900, 1500, TimingBasis.MEASURED)),
        ),
        total_duration_ms=1500,
    )
    proposal = build_storyboard_proposal(source)
    assert proposal.beats[0].timing.end_ms == 500
    assert proposal.beats[1].timing.start_ms == 900


def test_builder_rejects_mixed_timing_when_estimate_would_overlap_measured_anchor():
    source = NarrationSource(
        "s", "One. Two. Three.",
        (
            NarrationTextUnit("u1", 0, 4, TimingInterval(0, 5000, TimingBasis.MEASURED)),
            NarrationTextUnit("u2", 4, 9),
            NarrationTextUnit("u3", 9, 16, TimingInterval(6000, 7000, TimingBasis.MEASURED)),
        ),
        total_duration_ms=7000,
    )
    # The missing middle beat is estimated from the prior end and remains within
    # the next measured anchor only when its configured estimate fits.
    proposal = build_storyboard_proposal(
        source, config=StoryboardBuilderConfig(default_beat_duration_ms=500)
    )
    assert proposal.beats[1].timing == TimingInterval(5000, 5500, TimingBasis.ESTIMATED)
    assert proposal.beats[2].timing == source.units[2].timing


def test_empty_source_produces_empty_reviewable_proposal():
    source = NarrationSource("empty", "", ())
    proposal = build_storyboard_proposal(source)
    assert proposal.beats == ()
    assert proposal.review_status is ProposalReviewStatus.NEEDS_REVIEW
