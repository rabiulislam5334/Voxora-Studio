from __future__ import annotations

from dataclasses import replace

import pytest

from app.universal.narration_segmentation import segment_narration
from app.universal.storyboard import (
    ContinuityKind,
    ContinuityReference,
    NarrationSource,
    NarrationTextUnit,
    StoryboardBeat,
    StoryboardProposal,
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)
from app.universal.storyboard_builder import build_storyboard_proposal
from app.universal.storyboard_diagnostics import (
    StoryboardDiagnostic,
    StoryboardDiagnosticSeverity,
    diagnose_storyboard,
)


def build_source_and_proposal():
    source = segment_narration(
        "The door opens. A shadow crosses the hall.",
        source_id="diagnostic-source",
        total_duration_ms=4200,
    )
    return source, build_storyboard_proposal(source)


def test_diagnostics_are_deterministic_and_do_not_mutate_proposal():
    source, proposal = build_source_and_proposal()
    before = proposal.to_dict()
    first = diagnose_storyboard(proposal, source)
    second = diagnose_storyboard(proposal, source)
    assert first == second
    assert proposal.to_dict() == before
    assert all(isinstance(item, StoryboardDiagnostic) for item in first)


def test_reports_timeline_gaps_and_overlaps_with_stable_codes():
    source = NarrationSource(
        "s", "One. Two. Three.",
        (
            NarrationTextUnit("u1", 0, 4, TimingInterval(0, 500, TimingBasis.MEASURED)),
            NarrationTextUnit("u2", 4, 9, TimingInterval(700, 1200, TimingBasis.MEASURED)),
            NarrationTextUnit("u3", 9, 16, TimingInterval(1000, 1500, TimingBasis.MEASURED)),
        ),
        total_duration_ms=1500,
    )
    proposal = build_storyboard_proposal(source)
    diagnostics = diagnose_storyboard(proposal, source)
    assert [(item.code, item.subject_id, item.related_ids) for item in diagnostics
            if item.code in {"TIMELINE_GAP", "TIMELINE_OVERLAP"}] == [
        ("TIMELINE_GAP", "beat-0001", ("beat-0002",)),
        ("TIMELINE_OVERLAP", "beat-0002", ("beat-0003",)),
    ]


def test_reports_unmapped_and_reused_narration_units():
    source = segment_narration("One. Two. Three.", source_id="s")
    base = build_storyboard_proposal(source)
    beats = (
        replace(base.beats[0], narration_unit_ids=("unit-0001",)),
        replace(base.beats[1], narration_unit_ids=("unit-0001",)),
    )
    proposal = replace(base, beats=beats)
    diagnostics = diagnose_storyboard(proposal, source)
    assert any(item.code == "NARRATION_UNIT_UNMAPPED" and item.subject_id == "unit-0003"
               for item in diagnostics)
    reused = next(item for item in diagnostics if item.code == "NARRATION_UNIT_REUSED")
    assert reused.subject_id == "unit-0001"
    assert reused.related_ids == ("beat-0001", "beat-0002")


def test_reports_source_identity_mismatch_without_mutating_data():
    source, proposal = build_source_and_proposal()
    other = segment_narration("Different text.", source_id=source.source_id)
    diagnostics = diagnose_storyboard(proposal, other)
    assert diagnostics[0].code == "SOURCE_IDENTITY_MISMATCH"
    assert diagnostics[0].severity is StoryboardDiagnosticSeverity.ERROR


def test_reports_unused_continuity_references_and_estimated_timing():
    source = segment_narration("One.", source_id="s")
    reference = ContinuityReference("unused-prop", ContinuityKind.PROP, "A brass key")
    proposal = build_storyboard_proposal(source, continuity_references=(reference,))
    diagnostics = diagnose_storyboard(proposal, source)
    assert any(item.code == "CONTINUITY_REFERENCE_UNUSED"
               and item.subject_id == "unused-prop" for item in diagnostics)
    assert any(item.code == "TIMING_ESTIMATED" and item.subject_id == "beat-0001"
               for item in diagnostics)


def test_reports_timing_beyond_declared_narration_duration():
    source = NarrationSource(
        "s", "One.",
        (NarrationTextUnit("u1", 0, 4, TimingInterval(0, 1500, TimingBasis.MEASURED)),),
        total_duration_ms=1000,
    )
    # The source contract itself forbids a unit interval beyond its duration.
    # Construct a valid source with a longer unit then an independent beat interval.
    valid_source = NarrationSource(
        "s", "One.", (NarrationTextUnit("u1", 0, 4),), total_duration_ms=1000
    )
    base = build_storyboard_proposal(valid_source)
    long_beat = replace(base.beats[0], timing=TimingInterval(0, 1500, TimingBasis.MEASURED))
    proposal = replace(base, beats=(long_beat,))
    diagnostics = diagnose_storyboard(proposal, valid_source)
    assert any(item.code == "TIMING_EXCEEDS_SOURCE_DURATION"
               and item.subject_id == "beat-0001" for item in diagnostics)


def test_diagnostic_contract_validates_fields_and_input_types():
    with pytest.raises(StoryboardValidationError):
        StoryboardDiagnostic("", StoryboardDiagnosticSeverity.ERROR, "bad")
    with pytest.raises(StoryboardValidationError):
        diagnose_storyboard(object())  # type: ignore[arg-type]


def test_empty_proposal_has_no_diagnostics():
    source = NarrationSource("empty", "", ())
    proposal = build_storyboard_proposal(source)
    assert diagnose_storyboard(proposal, source) == ()
