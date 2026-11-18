"""Deterministic storyboard proposal construction from approved narration units.

This module creates reviewable visual-intent data only. It does not generate
images, animation, assets, narration, or render output.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from app.universal.storyboard import (
    ContinuityReference,
    NarrationSource,
    ProposalReviewStatus,
    StoryboardBeat,
    StoryboardProposal,
    StoryboardValidationError,
    TimingBasis,
    TimingInterval,
)


@dataclass(frozen=True)
class StoryboardBuilderConfig:
    """Deterministic timing fallback used only when narration timing is absent."""

    default_beat_duration_ms: int = 5000

    def __post_init__(self) -> None:
        value = self.default_beat_duration_ms
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise StoryboardValidationError(
                "default_beat_duration_ms must be a positive integer"
            )


def _validate_unit_mapping(
    value: Optional[Mapping[str, object]], known_ids: set[str], name: str
) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise StoryboardValidationError(f"{name} must be a mapping keyed by narration unit ID")
    unknown = sorted(set(value) - known_ids)
    if unknown:
        raise StoryboardValidationError(
            f"{name} contains unknown narration unit IDs: {', '.join(unknown)}"
        )
    return value


def _weighted_durations(source: NarrationSource) -> Tuple[int, ...]:
    """Allocate a supplied total duration by non-whitespace source characters."""
    units = source.units
    total = source.total_duration_ms
    if total is None:
        raise AssertionError("total duration is required")
    if total < len(units):
        raise StoryboardValidationError(
            "source total_duration_ms must provide at least 1 ms per storyboard beat"
        )
    weights = [
        max(1, sum(not char.isspace() for char in source.text_for_unit(unit)))
        for unit in units
    ]
    remaining = total - len(units)
    weight_total = sum(weights)
    exact = [remaining * weight / weight_total for weight in weights]
    floors = [int(value) for value in exact]
    durations = [1 + value for value in floors]
    leftover = total - sum(durations)
    order = sorted(
        range(len(units)), key=lambda index: (-(exact[index] - floors[index]), index)
    )
    for index in order[:leftover]:
        durations[index] += 1
    return tuple(durations)


def _resolve_timings(
    source: NarrationSource, config: StoryboardBuilderConfig
) -> Tuple[TimingInterval, ...]:
    units = source.units
    if not units:
        return ()
    supplied = [unit.timing is not None for unit in units]
    if all(supplied):
        return tuple(unit.timing for unit in units)  # type: ignore[misc]
    if not any(supplied):
        if source.total_duration_ms is not None:
            durations = _weighted_durations(source)
        else:
            durations = (config.default_beat_duration_ms,) * len(units)
        cursor = 0
        result = []
        for duration in durations:
            result.append(TimingInterval(cursor, cursor + duration, TimingBasis.ESTIMATED))
            cursor += duration
        return tuple(result)

    # Preserve every caller-supplied interval. Untimed units are estimated after
    # the latest preceding interval; if that collides with a later measured start,
    # reject rather than silently shifting measured audio timing.
    cursor = 0
    result = []
    for index, unit in enumerate(units):
        if unit.timing is not None:
            timing = unit.timing
            if timing.start_ms < cursor:
                raise StoryboardValidationError(
                    "mixed measured/estimated unit timings overlap; provide timings for every unit"
                )
        else:
            duration = config.default_beat_duration_ms
            if source.total_duration_ms is not None:
                remaining_units = len(units) - index
                remaining_ms = source.total_duration_ms - cursor
                if remaining_ms < remaining_units:
                    raise StoryboardValidationError(
                        "source total_duration_ms cannot fit estimated storyboard beats"
                    )
                duration = min(duration, remaining_ms - (remaining_units - 1))
            timing = TimingInterval(cursor, cursor + duration, TimingBasis.ESTIMATED)
        if source.total_duration_ms is not None and timing.end_ms > source.total_duration_ms:
            raise StoryboardValidationError("storyboard beat timing exceeds source total_duration_ms")
        result.append(timing)
        cursor = timing.end_ms
    return tuple(result)


def build_storyboard_proposal(
    source: NarrationSource,
    *,
    visual_descriptions: Optional[Mapping[str, str]] = None,
    action_cues: Optional[Mapping[str, Sequence[str]]] = None,
    continuity_references: Sequence[ContinuityReference] = (),
    continuity_reference_ids: Optional[Mapping[str, Sequence[str]]] = None,
    config: Optional[StoryboardBuilderConfig] = None,
) -> StoryboardProposal:
    """Build one deterministic visual beat per narration unit.

    Explicit visual descriptions/action cues are accepted as caller-authored
    intent. When no description is supplied, the beat clearly labels the exact
    narration slice as a visual direction prompt; no semantic scene is invented.
    Missing timings use the source total duration when available, otherwise the
    configured fixed estimate. All generated timings retain ESTIMATED provenance.
    """
    if not isinstance(source, NarrationSource):
        raise StoryboardValidationError("source must be a NarrationSource")
    if config is None:
        config = StoryboardBuilderConfig()
    if not isinstance(config, StoryboardBuilderConfig):
        raise StoryboardValidationError("config must be a StoryboardBuilderConfig")

    known_ids = {unit.unit_id for unit in source.units}
    descriptions = _validate_unit_mapping(visual_descriptions, known_ids, "visual_descriptions")
    cues_by_unit = _validate_unit_mapping(action_cues, known_ids, "action_cues")
    refs_by_unit = _validate_unit_mapping(
        continuity_reference_ids, known_ids, "continuity_reference_ids"
    )
    references = tuple(continuity_references)
    if not all(isinstance(ref, ContinuityReference) for ref in references):
        raise StoryboardValidationError(
            "continuity_references must contain ContinuityReference values"
        )
    known_refs = {ref.reference_id for ref in references}
    if len(known_refs) != len(references):
        raise StoryboardValidationError("continuity_references must not contain duplicate IDs")

    timings = _resolve_timings(source, config)
    beats = []
    for index, (unit, timing) in enumerate(zip(source.units, timings), start=1):
        unit_text = source.text_for_unit(unit)
        description = descriptions.get(unit.unit_id)
        if description is None:
            description = f"Visual direction based on narration: {unit_text.strip() or '[empty text]'}"
        if not isinstance(description, str) or not description.strip():
            raise StoryboardValidationError(
                f"visual_descriptions[{unit.unit_id}] must be a non-empty string"
            )
        cues = cues_by_unit.get(unit.unit_id, ())
        if isinstance(cues, (str, bytes)) or not isinstance(cues, Sequence):
            raise StoryboardValidationError(
                f"action_cues[{unit.unit_id}] must be a sequence of strings"
            )
        if not all(isinstance(cue, str) and cue.strip() for cue in cues):
            raise StoryboardValidationError(
                f"action_cues[{unit.unit_id}] must contain non-empty strings"
            )
        ref_ids = refs_by_unit.get(unit.unit_id, ())
        if isinstance(ref_ids, (str, bytes)) or not isinstance(ref_ids, Sequence):
            raise StoryboardValidationError(
                f"continuity_reference_ids[{unit.unit_id}] must be a sequence of IDs"
            )
        if not all(isinstance(ref_id, str) and ref_id in known_refs for ref_id in ref_ids):
            raise StoryboardValidationError(
                f"continuity_reference_ids[{unit.unit_id}] contains an unresolved reference"
            )
        beats.append(
            StoryboardBeat(
                beat_id=f"beat-{index:04d}",
                narration_unit_ids=(unit.unit_id,),
                visual_description=description,
                timing=timing,
                action_cues=tuple(cues),
                continuity_reference_ids=tuple(ref_ids),
                metadata={
                    "source_start_offset": unit.start_offset,
                    "source_end_offset": unit.end_offset,
                    "timing_source": (
                        "narration_unit" if unit.timing is not None
                        else "estimated_from_total_duration"
                        if source.total_duration_ms is not None
                        else "configured_default_estimate"
                    ),
                },
            )
        )

    identity_payload = {
        "source_id": source.source_id,
        "source_fingerprint": source.source_fingerprint,
        "config": {"default_beat_duration_ms": config.default_beat_duration_ms},
        "beats": [beat.to_dict() for beat in beats],
        "continuity_references": [ref.to_dict() for ref in references],
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    proposal = StoryboardProposal(
        proposal_id=f"proposal-{digest[:24]}",
        source_id=source.source_id,
        source_fingerprint=source.source_fingerprint,
        beats=tuple(beats),
        review_status=ProposalReviewStatus.NEEDS_REVIEW,
        continuity_references=references,
        metadata={
            "builder": "deterministic_narration_to_storyboard_v1",
            "beat_count": len(beats),
            "timing_fallback_ms": config.default_beat_duration_ms,
            "requires_human_review": True,
        },
    )
    proposal.validate_against(source)
    return proposal
