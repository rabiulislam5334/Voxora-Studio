from __future__ import annotations

import copy
import hashlib

import pytest

from app.universal.storyboard import (
    ContinuityKind,
    ContinuityReference,
    NarrationSource,
    NarrationTextUnit,
    ProposalReviewStatus,
    StoryboardBeat,
    StoryboardProposal,
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)


def sample_source():
    text = "The door opens. A shadow crosses the hall."
    first = text[:16]
    second = text[17:]
    return NarrationSource(
        source_id="narration-01",
        text=text,
        units=(
            NarrationTextUnit("unit-01", 0, 16, TimingInterval(0, 1800, TimingBasis.MEASURED)),
            NarrationTextUnit("unit-02", 17, len(text), TimingInterval(1800, 4200, TimingBasis.ESTIMATED)),
        ),
        language="en",
        total_duration_ms=4200,
        metadata={"origin": "user_script"},
    )


def sample_proposal(source=None):
    source = source or sample_source()
    character = ContinuityReference("shadow", ContinuityKind.CHARACTER, "A distant human silhouette")
    beat = StoryboardBeat(
        "beat-01", ("unit-01", "unit-02"), "A dark hallway as the door slowly opens.",
        TimingInterval(0, 4200, TimingBasis.ESTIMATED),
        ("door opens", "shadow crosses frame"), ("shadow",),
    )
    return StoryboardProposal(
        "proposal-01", source.source_id, source.source_fingerprint, (beat,),
        ProposalReviewStatus.NEEDS_REVIEW, (character,),
    )


def test_narration_source_preserves_exact_text_slices_and_round_trips():
    source = sample_source()
    assert source.text_for_unit(source.units[0]) == "The door opens."
    assert source.text_for_unit(source.units[1]) == "A shadow crosses the hall."
    assert NarrationSource.from_dict(source.to_dict()).to_dict() == source.to_dict()


def test_source_fingerprint_is_stable_sha256_of_exact_utf8_text():
    source = sample_source()
    assert source.source_fingerprint == hashlib.sha256(source.text.encode("utf-8")).hexdigest()


def test_text_unit_offsets_reject_out_of_range_and_overlap():
    with pytest.raises(StoryboardValidationError, match="exceed"):
        NarrationSource("s", "short", (NarrationTextUnit("u", 0, 99),))
    with pytest.raises(StoryboardValidationError, match="non-overlapping"):
        NarrationSource("s", "abcdef", (
            NarrationTextUnit("u1", 0, 4), NarrationTextUnit("u2", 3, 6)
        ))


def test_timing_uses_integer_milliseconds_and_explicit_provenance():
    timing = TimingInterval(125, 875, TimingBasis.ESTIMATED)
    assert timing.duration_ms == 750
    assert TimingInterval.from_dict(timing.to_dict()) == timing
    with pytest.raises(StoryboardValidationError, match="integer"):
        TimingInterval(0.5, 1000, TimingBasis.MEASURED)


def test_narration_timing_must_be_ordered_and_within_total_duration():
    with pytest.raises(StoryboardValidationError, match="ordered"):
        NarrationSource("s", "abcdef", (
            NarrationTextUnit("u1", 0, 3, TimingInterval(1000, 2000, TimingBasis.MEASURED)),
            NarrationTextUnit("u2", 3, 6, TimingInterval(500, 1500, TimingBasis.MEASURED)),
        ))
    with pytest.raises(StoryboardValidationError, match="exceeds"):
        NarrationSource("s", "abc", (
            NarrationTextUnit("u", 0, 3, TimingInterval(0, 2000, TimingBasis.MEASURED)),
        ), total_duration_ms=1000)


def test_proposal_validates_source_and_round_trips():
    source = sample_source()
    proposal = sample_proposal(source)
    proposal.validate_against(source)
    restored = StoryboardProposal.from_dict(proposal.to_dict())
    assert restored.to_dict() == proposal.to_dict()
    assert restored.review_status is ProposalReviewStatus.NEEDS_REVIEW


def test_proposal_rejects_stale_or_different_source_fingerprint():
    proposal = sample_proposal()
    changed = NarrationSource("narration-01", "Different narration", ())
    with pytest.raises(StoryboardValidationError, match="fingerprint"):
        proposal.validate_against(changed)


def test_proposal_rejects_unknown_narration_units_and_unresolved_refs():
    source = sample_source()
    bad_beat = StoryboardBeat(
        "beat-x", ("missing-unit",), "A visual.", TimingInterval(0, 100, TimingBasis.ESTIMATED)
    )
    proposal = StoryboardProposal(
        "p", source.source_id, source.source_fingerprint, (bad_beat,)
    )
    with pytest.raises(StoryboardValidationError, match="unknown narration units"):
        proposal.validate_against(source)

    with pytest.raises(StoryboardValidationError, match="unresolved continuity"):
        StoryboardProposal(
            "p2", source.source_id, source.source_fingerprint,
            (StoryboardBeat("b", ("u",), "Visual.", TimingInterval(0, 100, TimingBasis.ESTIMATED),
                            continuity_reference_ids=("missing",)),),
        )


def test_duplicate_ids_and_invalid_metadata_are_rejected():
    with pytest.raises(StoryboardValidationError, match="unique"):
        NarrationSource("s", "abcd", (
            NarrationTextUnit("same", 0, 2), NarrationTextUnit("same", 2, 4)
        ))
    with pytest.raises(StoryboardValidationError, match="JSON-compatible"):
        ContinuityReference("r", ContinuityKind.PROP, "A key", {"callable": lambda: None})


def test_unknown_metadata_is_preserved_without_mutating_input():
    source = sample_source()
    raw = source.to_dict()
    raw["future_field"] = {"retain": [1, 2]}
    original = copy.deepcopy(raw)
    restored = NarrationSource.from_dict(raw)
    assert raw == original
    assert restored.to_dict()["metadata"] == raw["metadata"]


def test_proposal_serialization_is_deterministic():
    proposal = sample_proposal()
    assert proposal.to_dict() == StoryboardProposal.from_dict(proposal.to_dict()).to_dict()
