"""Deterministic narration segmentation with exact source offsets.

No text is rewritten, normalized, synthesized, or sent to an external service.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from app.universal.storyboard import (
    NarrationSource,
    NarrationTextUnit,
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)


_CLOSING_PUNCTUATION = '"\'”’)]}'
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs",
    "etc", "e.g", "i.e", "u.s", "u.k",
})


@dataclass(frozen=True)
class NarrationSegmentationConfig:
    """Stable segmentation rules; max length is a soft boundary preference."""

    split_sentences: bool = True
    split_paragraphs: bool = True
    max_chars_per_unit: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.split_sentences, bool) or not isinstance(self.split_paragraphs, bool):
            raise StoryboardValidationError("segmentation split flags must be booleans")
        if self.max_chars_per_unit is not None and (
            isinstance(self.max_chars_per_unit, bool)
            or not isinstance(self.max_chars_per_unit, int)
            or self.max_chars_per_unit < 1
        ):
            raise StoryboardValidationError("max_chars_per_unit must be a positive integer or null")


def _is_sentence_boundary(text: str, punctuation_end: int) -> bool:
    cursor = punctuation_end
    while cursor < len(text) and text[cursor] in _CLOSING_PUNCTUATION:
        cursor += 1
    if cursor >= len(text) or not text[cursor].isspace():
        return False
    # Let the paragraph boundary own blank-line separators; avoid whitespace-only units.
    whitespace_end = cursor
    while whitespace_end < len(text) and text[whitespace_end].isspace():
        whitespace_end += 1
    if len(re.findall(r"\\r?\\n", text[cursor:whitespace_end])) >= 2:
        return False
    # A period in a decimal or a common title/abbreviation is not a sentence end.
    if text[punctuation_end - 1] == ".":
        previous = text[punctuation_end - 2] if punctuation_end >= 2 else ""
        following_index = cursor
        while following_index < len(text) and text[following_index].isspace():
            following_index += 1
        following = text[following_index:following_index + 1]
        if previous.isdigit() and following.isdigit():
            return False
        token_match = re.search(r"([A-Za-z](?:[A-Za-z.]*)?)$", text[:punctuation_end - 1])
        if token_match and token_match.group(1).lower().rstrip(".") in _ABBREVIATIONS:
            return False
    return True


def _base_spans(text: str, config: NarrationSegmentationConfig) -> list[tuple[int, int]]:
    if not text:
        return []
    boundaries = set()
    if config.split_sentences:
        index = 0
        while index < len(text):
            if text[index] in ".!?":
                end = index + 1
                while end < len(text) and text[end] in ".!?":
                    end += 1
                if _is_sentence_boundary(text, end):
                    while end < len(text) and text[end] in _CLOSING_PUNCTUATION:
                        end += 1
                    boundaries.add(end)
                index = end
            else:
                index += 1
    if config.split_paragraphs:
        for match in re.finditer(r"(?:\r?\n[ \t]*){2,}", text):
            boundaries.add(match.end())
    boundaries = sorted(point for point in boundaries if 0 < point < len(text))
    spans = []
    start = 0
    for end in boundaries:
        if end > start:
            spans.append((start, end))
            start = end
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _split_oversized(
    text: str, spans: list[tuple[int, int]], max_chars: Optional[int]
) -> list[tuple[int, int]]:
    if max_chars is None:
        return spans
    result = []
    for span_start, span_end in spans:
        start = span_start
        while span_end - start > max_chars:
            hard_limit = start + max_chars
            # Prefer the last whitespace boundary inside the configured window.
            split_at = hard_limit
            for cursor in range(hard_limit, start, -1):
                if text[cursor - 1].isspace():
                    split_at = cursor
                    break
            if split_at <= start:
                split_at = hard_limit
            result.append((start, split_at))
            start = split_at
        if start < span_end:
            result.append((start, span_end))
    return result


def _estimated_durations(text: str, spans: list[tuple[int, int]], total_ms: int) -> list[int]:
    if total_ms < len(spans):
        raise StoryboardValidationError(
            "total_duration_ms must provide at least 1 ms for every narration unit"
        )
    weights = [max(1, sum(not char.isspace() for char in text[start:end]))
               for start, end in spans]
    remaining = total_ms - len(spans)
    weight_total = sum(weights)
    exact = [remaining * weight / weight_total for weight in weights]
    floors = [int(value) for value in exact]
    durations = [1 + value for value in floors]
    leftover = total_ms - sum(durations)
    order = sorted(range(len(spans)), key=lambda i: (-(exact[i] - floors[i]), i))
    for index in order[:leftover]:
        durations[index] += 1
    return durations


def segment_narration(
    text: str,
    *,
    source_id: str,
    language: Optional[str] = None,
    total_duration_ms: Optional[int] = None,
    measured_timings: Optional[Mapping[str, TimingInterval]] = None,
    config: Optional[NarrationSegmentationConfig] = None,
) -> NarrationSource:
    """Create deterministic text units while preserving every source character.

    Measured timings are keyed by generated unit ID (unit-0001, ...). They must
    cover every generated unit and use MEASURED provenance. If only total
    duration is provided, duration is distributed by non-whitespace character
    count using largest-remainder integer allocation; all results are ESTIMATED.
    """
    if not isinstance(text, str):
        raise StoryboardValidationError("narration text must be a string")
    if not isinstance(source_id, str) or not source_id.strip():
        raise StoryboardValidationError("source_id must be a non-empty string")
    if total_duration_ms is not None and (
        isinstance(total_duration_ms, bool)
        or not isinstance(total_duration_ms, int)
        or total_duration_ms <= 0
    ):
        raise StoryboardValidationError("total_duration_ms must be a positive integer or null")
    if config is None:
        config = NarrationSegmentationConfig()
    if not isinstance(config, NarrationSegmentationConfig):
        raise StoryboardValidationError("config must be a NarrationSegmentationConfig")

    spans = _split_oversized(text, _base_spans(text, config), config.max_chars_per_unit)
    if measured_timings is not None and not isinstance(measured_timings, Mapping):
        raise StoryboardValidationError("measured_timings must be a mapping keyed by unit ID")
    unit_ids = [f"unit-{index:04d}" for index in range(1, len(spans) + 1)]
    timings: list[Optional[TimingInterval]] = [None] * len(spans)

    if measured_timings is not None:
        if set(measured_timings) != set(unit_ids):
            raise StoryboardValidationError("measured_timings must cover every generated unit ID exactly")
        for index, unit_id in enumerate(unit_ids):
            timing = measured_timings[unit_id]
            if not isinstance(timing, TimingInterval) or timing.basis is not TimingBasis.MEASURED:
                raise StoryboardValidationError("every supplied unit timing must use MEASURED provenance")
            timings[index] = timing
    elif total_duration_ms is not None and spans:
        durations = _estimated_durations(text, spans, total_duration_ms)
        cursor = 0
        for index, duration in enumerate(durations):
            timings[index] = TimingInterval(cursor, cursor + duration, TimingBasis.ESTIMATED)
            cursor += duration

    units: Tuple[NarrationTextUnit, ...] = tuple(
        NarrationTextUnit(unit_id, start, end, timings[index])
        for index, (unit_id, (start, end)) in enumerate(zip(unit_ids, spans))
    )
    if measured_timings is not None and total_duration_ms is not None and any(
        timing.end_ms > total_duration_ms for timing in timings if timing is not None
    ):
        raise StoryboardValidationError("measured unit timing exceeds total_duration_ms")

    return NarrationSource(
        source_id=source_id,
        text=text,
        units=units,
        language=language,
        total_duration_ms=total_duration_ms,
        metadata={
            "segmentation": {
                "algorithm": "deterministic_sentence_paragraph_v1",
                "split_sentences": config.split_sentences,
                "split_paragraphs": config.split_paragraphs,
                "max_chars_per_unit": config.max_chars_per_unit,
                "timing_strategy": (
                    "measured" if measured_timings is not None
                    else "largest_remainder_non_whitespace_char_weight"
                    if total_duration_ms is not None and spans
                    else "not_supplied"
                ),
            }
        },
    )
