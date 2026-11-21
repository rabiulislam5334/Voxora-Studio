import pytest

from app.universal.supplied_narration_input import (
    SuppliedNarrationInputError,
    build_line_aligned_narration_source,
)


def test_builds_one_exact_narration_unit_per_alignment_line():
    script = "First sentence. Second sentence!\n\nA final paragraph."
    aligned, source = build_line_aligned_narration_source(script, language="en")

    assert aligned == "First sentence.\nSecond sentence!\nA final paragraph."
    assert len(source.units) == 3
    assert [source.text_for_unit(unit) for unit in source.units] == [
        "First sentence.", "Second sentence!", "A final paragraph.",
    ]
    assert source.language == "en"
    assert source.metadata["source_wording_preserved"] is True
    assert source.metadata["whitespace_normalized"] is True


@pytest.mark.parametrize(
    ("script", "language"),
    [("", "en"), ("   ", "en"), ("A script.", ""), ("A script.", "  ")],
)
def test_rejects_empty_script_or_language(script, language):
    with pytest.raises(SuppliedNarrationInputError):
        build_line_aligned_narration_source(script, language=language)


def test_normalization_does_not_rewrite_words():
    script = "  Keep   every word.\n\nDo not replace the narration! "
    aligned, source = build_line_aligned_narration_source(script, language="en")
    assert aligned == "Keep every word.\nDo not replace the narration!"
    assert "replace" in source.text
    assert len(source.units) == 2
