from pathlib import Path

import pytest

from app.universal.cinematic_skill_timing import (
    CinematicLineCue,
    CinematicSkillNarrationDoc,
    CinematicSkillTimingError,
    CinematicWordCue,
)


def test_line_and_word_cues_return_exact_supplied_timestamps(tmp_path):
    doc = CinematicSkillNarrationDoc(
        tmp_path,
        [
            CinematicLineCue(
                7, 1.2, 3.0, "The Voyager crossed the heliopause.",
                (
                    CinematicWordCue("The", 1.21, 1.35),
                    CinematicWordCue("Voyager", 1.36, 1.82),
                    CinematicWordCue("crossed", 1.83, 2.1),
                    CinematicWordCue("the", 2.11, 2.2),
                    CinematicWordCue("heliopause.", 2.21, 2.9),
                ),
            )
        ],
    )

    assert doc.L(7) == 1.2
    assert doc.E(7) == 3.0
    assert doc.W(7, "Voyager") == 1.36
    assert doc.W(7, "the", nth=1) == 2.11


def test_word_lookup_is_unicode_aware_and_does_not_estimate_missing_words(tmp_path):
    doc = CinematicSkillNarrationDoc(
        tmp_path,
        [
            CinematicLineCue(
                1, 0.0, 2.0, "বাংলা narration",
                (CinematicWordCue("বাংলা", 0.1, 0.8),),
            )
        ],
    )

    assert doc.W(1, "বাংলা") == 0.1
    with pytest.raises(CinematicSkillTimingError, match="no measured timestamp"):
        doc.W(1, "narration")


def test_invalid_or_out_of_line_word_timing_is_rejected(tmp_path):
    with pytest.raises(CinematicSkillTimingError, match="inside its parent line"):
        CinematicLineCue(
            1, 1.0, 2.0, "hello",
            (CinematicWordCue("hello", 0.5, 1.5),),
        )


def test_duplicate_line_ids_and_unknown_line_ids_are_rejected(tmp_path):
    line = CinematicLineCue(1, 0.0, 1.0, "hello")
    with pytest.raises(CinematicSkillTimingError, match="unique"):
        CinematicSkillNarrationDoc(tmp_path, [line, line])

    doc = CinematicSkillNarrationDoc(tmp_path, [line])
    with pytest.raises(CinematicSkillTimingError, match="unknown narration line"):
        doc.L(99)


def test_map_names_cannot_escape_prepared_assets_directory(tmp_path):
    doc = CinematicSkillNarrationDoc(
        tmp_path, [CinematicLineCue(1, 0.0, 1.0, "hello")]
    )
    with pytest.raises(CinematicSkillTimingError, match="simple file stem"):
        doc.map("../outside")
