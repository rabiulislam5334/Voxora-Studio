"""Deterministic, read-only storyboard continuity and timing diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from app.universal.storyboard import (
    NarrationSource,
    StoryboardProposal,
    StoryboardValidationError,
    TimingBasis,
)


class StoryboardDiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class StoryboardDiagnostic:
    """Stable, renderer-independent finding; diagnostics never mutate inputs."""

    code: str
    severity: StoryboardDiagnosticSeverity
    message: str
    subject_id: Optional[str] = None
    related_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise StoryboardValidationError("diagnostic.code must be a non-empty string")
        if not isinstance(self.severity, StoryboardDiagnosticSeverity):
            raise StoryboardValidationError("diagnostic.severity is unsupported")
        if not isinstance(self.message, str) or not self.message.strip():
            raise StoryboardValidationError("diagnostic.message must be a non-empty string")
        if self.subject_id is not None and (
            not isinstance(self.subject_id, str) or not self.subject_id.strip()
        ):
            raise StoryboardValidationError("diagnostic.subject_id must be a non-empty string or null")
        related = tuple(self.related_ids)
        if not all(isinstance(item, str) and item.strip() for item in related):
            raise StoryboardValidationError("diagnostic.related_ids must contain non-empty strings")
        object.__setattr__(self, "related_ids", related)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "subject_id": self.subject_id,
            "related_ids": list(self.related_ids),
        }


def diagnose_storyboard(
    proposal: StoryboardProposal,
    source: Optional[NarrationSource] = None,
    available_continuity_reference_ids: Optional[Sequence[str]] = None,
) -> Tuple[StoryboardDiagnostic, ...]:
    """Return stable findings for timing, narration coverage, and continuity usage.

    The function is pure: it does not repair, reorder, approve, or mutate a
    proposal. Structural contract violations that cannot exist in a valid
    StoryboardProposal are rejected at construction time by that contract.
    """
    if not isinstance(proposal, StoryboardProposal):
        raise StoryboardValidationError("proposal must be a StoryboardProposal")
    if source is not None and not isinstance(source, NarrationSource):
        raise StoryboardValidationError("source must be a NarrationSource or null")
    if available_continuity_reference_ids is None:
        available_reference_ids = None
    else:
        if isinstance(available_continuity_reference_ids, (str, bytes)):
            raise StoryboardValidationError(
                "available_continuity_reference_ids must be a sequence of IDs"
            )
        available_reference_ids = tuple(available_continuity_reference_ids)
        if not all(isinstance(item, str) and item.strip() for item in available_reference_ids):
            raise StoryboardValidationError(
                "available_continuity_reference_ids must contain non-empty strings"
            )
        if len(set(available_reference_ids)) != len(available_reference_ids):
            raise StoryboardValidationError(
                "available_continuity_reference_ids must not contain duplicates"
            )
        available_reference_ids = set(available_reference_ids)

    findings = []
    if source is not None:
        if source.source_id != proposal.source_id or source.source_fingerprint != proposal.source_fingerprint:
            findings.append(StoryboardDiagnostic(
                "SOURCE_IDENTITY_MISMATCH", StoryboardDiagnosticSeverity.ERROR,
                "The narration source identity or fingerprint does not match this proposal.",
                proposal.proposal_id,
            ))
        else:
            known_units = {unit.unit_id for unit in source.units}
            used_units = {
                unit_id for beat in proposal.beats for unit_id in beat.narration_unit_ids
            }
            for unit_id in sorted(known_units - used_units):
                findings.append(StoryboardDiagnostic(
                    "NARRATION_UNIT_UNMAPPED", StoryboardDiagnosticSeverity.WARNING,
                    "A narration unit is not represented by any storyboard beat.", unit_id,
                ))
            occurrences = {}
            for beat in proposal.beats:
                for unit_id in beat.narration_unit_ids:
                    occurrences.setdefault(unit_id, []).append(beat.beat_id)
            for unit_id in sorted(occurrences):
                beat_ids = occurrences[unit_id]
                if len(beat_ids) > 1:
                    findings.append(StoryboardDiagnostic(
                        "NARRATION_UNIT_REUSED", StoryboardDiagnosticSeverity.INFO,
                        "A narration unit is referenced by multiple visual beats; confirm this is intentional.",
                        unit_id, tuple(beat_ids),
                    ))

    beats = proposal.beats
    for previous, current in zip(beats, beats[1:]):
        delta = current.timing.start_ms - previous.timing.end_ms
        if delta > 0:
            findings.append(StoryboardDiagnostic(
                "TIMELINE_GAP", StoryboardDiagnosticSeverity.WARNING,
                f"There is an uncovered timeline gap of {delta} ms between adjacent storyboard beats.",
                previous.beat_id, (current.beat_id,),
            ))
        elif delta < 0:
            findings.append(StoryboardDiagnostic(
                "TIMELINE_OVERLAP", StoryboardDiagnosticSeverity.WARNING,
                f"Adjacent storyboard beats overlap by {-delta} ms.",
                previous.beat_id, (current.beat_id,),
            ))

    if source is not None and (
        source.source_id == proposal.source_id
        and source.source_fingerprint == proposal.source_fingerprint
        and source.total_duration_ms is not None
    ):
        for beat in beats:
            if beat.timing.end_ms > source.total_duration_ms:
                findings.append(StoryboardDiagnostic(
                    "TIMING_EXCEEDS_SOURCE_DURATION", StoryboardDiagnosticSeverity.ERROR,
                    "The storyboard beat extends beyond the declared narration duration.",
                    beat.beat_id,
                ))

    referenced_ids = {
        reference_id
        for beat in beats
        for reference_id in beat.continuity_reference_ids
    }
    for reference in sorted(proposal.continuity_references, key=lambda item: item.reference_id):
        if reference.reference_id not in referenced_ids:
            findings.append(StoryboardDiagnostic(
                "CONTINUITY_REFERENCE_UNUSED", StoryboardDiagnosticSeverity.INFO,
                "This declared continuity reference is not used by any storyboard beat.",
                reference.reference_id,
            ))

    if available_reference_ids is not None:
        for reference_id in sorted(referenced_ids - available_reference_ids):
            findings.append(StoryboardDiagnostic(
                "CONTINUITY_REFERENCE_UNRESOLVED", StoryboardDiagnosticSeverity.ERROR,
                "A storyboard beat references an ID that is absent from the supplied continuity catalog.",
                reference_id,
            ))

    for beat in beats:
        if beat.timing.basis is TimingBasis.ESTIMATED:
            findings.append(StoryboardDiagnostic(
                "TIMING_ESTIMATED", StoryboardDiagnosticSeverity.INFO,
                "This beat uses estimated timing; verify it against the final narration audio.",
                beat.beat_id,
            ))

    return tuple(findings)
