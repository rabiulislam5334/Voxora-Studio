"""Input preparation for the supplied-audio Auto Produce workflow.

The current local aligner returns one timing line per non-empty script line.
This adapter converts the canonical sentence segmentation into that exact
line contract without changing spoken wording. Non-spoken pause/style markup is
removed through the existing narration parser; whitespace is normalized for alignment.
"""
from __future__ import annotations

from app.text.narration_parser import TextItem, parse_script
from app.universal.narration_segmentation import segment_narration
from app.universal.storyboard import NarrationSource, NarrationTextUnit


class SuppliedNarrationInputError(ValueError):
    """Raised when script text cannot form a usable narration source."""


def build_line_aligned_narration_source(
    script: str,
    *,
    language: str,
    source_id: str = "auto-produce-source",
) -> tuple[str, NarrationSource]:
    """Return normalized alignment text and exact ordered narration units.

    Sentence segmentation is delegated to the existing canonical segmenter.
    The resulting sentence text is joined with newlines because the current
    Stable-ts adapter preserves one aligned segment per non-empty input line.
    No words are added, removed, or rewritten.
    """
    if not isinstance(script, str) or not script.strip():
        raise SuppliedNarrationInputError("project script is empty")
    if not isinstance(language, str) or not language.strip():
        raise SuppliedNarrationInputError("narration language is required")

    parsed = parse_script(script)
    spoken_paragraphs = [
        " ".join(item.text for item in paragraph.items if isinstance(item, TextItem))
        for paragraph in parsed.paragraphs
    ]
    spoken_script = "\n\n".join(text for text in spoken_paragraphs if text.strip())
    if not spoken_script.strip():
        raise SuppliedNarrationInputError("project script contains no spoken text after removing narration markup")

    segmented = segment_narration(
        spoken_script,
        source_id=source_id,
        language=language.strip(),
    )
    lines = [
        " ".join(segmented.text_for_unit(unit).split())
        for unit in segmented.units
    ]
    lines = [line for line in lines if line]
    if not lines:
        raise SuppliedNarrationInputError("project script contains no alignable narration text")

    normalized = "\n".join(lines)
    units = []
    cursor = 0
    for index, line in enumerate(lines, start=1):
        start = cursor
        end = start + len(line)
        units.append(NarrationTextUnit(
            unit_id=f"unit-{index:04d}",
            start_offset=start,
            end_offset=end,
        ))
        cursor = end + (1 if index < len(lines) else 0)

    source = NarrationSource(
        source_id=source_id,
        text=normalized,
        units=tuple(units),
        language=language.strip(),
        metadata={
            "alignment_input": "one_sentence_per_line_v1",
            "source_wording_preserved": True,
            "narration_markup_removed": True,
            "whitespace_normalized": True,
        },
    )
    return normalized, source
