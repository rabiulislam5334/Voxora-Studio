from __future__ import annotations

import pytest

from app.universal.narration_segmentation import (
    NarrationSegmentationConfig,
    segment_narration,
)
from app.universal.storyboard import (
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)


def slices(source):
    return [source.text_for_unit(unit) for unit in source.units]


def test_sentence_segmentation_preserves_exact_source_text_and_offsets():
    text = 'Hello, world!  "How are you?" I am fine.\nLast line.'
    source = segment_narration(text, source_id="script-01")
    assert slices(source) == ["Hello, world!", '  "How are you?"', " I am fine.", "\nLast line."]
    assert "".join(slices(source)) == text
    assert [(u.start_offset, u.end_offset) for u in source.units] == [
        (0, 13), (13, 29), (29, 40), (40, len(text))
    ]


def test_paragraph_boundaries_are_preserved_in_source_order():
    text = "First paragraph.\n\nSecond paragraph without punctuation\n\nThird."
    source = segment_narration(text, source_id="paragraphs")
    assert "".join(slices(source)) == text
    assert len(source.units) == 3


def test_empty_and_whitespace_only_input_are_safe_and_lossless():
    empty = segment_narration("", source_id="empty")
    assert empty.units == ()
    whitespace = segment_narration("  \n\t", source_id="space")
    assert "".join(slices(whitespace)) == "  \n\t"
    assert len(whitespace.units) == 1


def test_max_chars_uses_whitespace_preference_without_losing_characters():
    text = "A long narration sentence that needs smaller chunks."
    source = segment_narration(
        text, source_id="bounded",
        config=NarrationSegmentationConfig(max_chars_per_unit=12),
    )
    assert "".join(slices(source)) == text
    assert all(unit.end_offset - unit.start_offset <= 12 for unit in source.units)


def test_decimal_and_common_titles_do_not_create_false_sentence_boundaries():
    text = "Dr. Smith measured 3.14 cm. Then he left."
    source = segment_narration(text, source_id="abbreviations")
    assert len(source.units) == 2
    assert slices(source)[0] == "Dr. Smith measured 3.14 cm."


def test_total_duration_is_distributed_as_deterministic_estimates():
    text = "Short. A considerably longer sentence."
    first = segment_narration(text, source_id="timed", total_duration_ms=5001)
    second = segment_narration(text, source_id="timed", total_duration_ms=5001)
    assert first.to_dict() == second.to_dict()
    assert all(unit.timing.basis is TimingBasis.ESTIMATED for unit in first.units)
    assert sum(unit.timing.duration_ms for unit in first.units) == 5001
    assert first.units[0].timing.start_ms == 0
    assert first.units[-1].timing.end_ms == 5001


def test_too_short_total_duration_is_rejected_instead_of_fabricating_zero_length():
    with pytest.raises(StoryboardValidationError, match="at least 1 ms"):
        segment_narration("One. Two.", source_id="tiny", total_duration_ms=1)


def test_measured_timings_are_preserved_and_must_cover_all_units():
    text = "First. Second."
    timings = {
        "unit-0001": TimingInterval(100, 900, TimingBasis.MEASURED),
        "unit-0002": TimingInterval(900, 2100, TimingBasis.MEASURED),
    }
    source = segment_narration(text, source_id="measured", measured_timings=timings)
    assert [unit.timing for unit in source.units] == list(timings.values())
    with pytest.raises(StoryboardValidationError, match="cover every"):
        segment_narration(text, source_id="partial", measured_timings={"unit-0001": timings["unit-0001"]})


def test_measured_timings_require_measured_basis_and_duration_bounds():
    with pytest.raises(StoryboardValidationError, match="MEASURED"):
        segment_narration(
            "One.", source_id="wrong-basis",
            measured_timings={"unit-0001": TimingInterval(0, 100, TimingBasis.ESTIMATED)},
        )
    with pytest.raises(StoryboardValidationError, match="exceeds"):
        segment_narration(
            "One.", source_id="outside", total_duration_ms=100,
            measured_timings={"unit-0001": TimingInterval(0, 200, TimingBasis.MEASURED)},
        )


def test_configuration_validation_and_deterministic_ids():
    with pytest.raises(StoryboardValidationError, match="positive integer"):
        NarrationSegmentationConfig(max_chars_per_unit=0)
    first = segment_narration("One. Two.", source_id="stable")
    second = segment_narration("One. Two.", source_id="stable")
    assert [unit.unit_id for unit in first.units] == ["unit-0001", "unit-0002"]
    assert first.to_dict() == second.to_dict()
