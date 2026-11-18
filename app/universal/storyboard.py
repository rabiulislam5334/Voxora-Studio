"""Immutable, renderer-independent narration and storyboard planning contracts.

These contracts preserve source narration and timing provenance. They describe
creative intent only; they do not generate assets, select engines, or render.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Tuple


STORYBOARD_PROPOSAL_VERSION = 1
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class StoryboardValidationError(ValueError):
    """Raised when narration or storyboard contract data is invalid."""


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        raise StoryboardValidationError(f"{name} must be a stable non-empty identifier")
    return value


def _text(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise StoryboardValidationError(f"{name} must be a {'string' if allow_empty else 'non-empty string'}")
    return value


def _json_value(value: Any, path: str = "metadata") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return copy.deepcopy(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StoryboardValidationError(f"{path} must not contain NaN or infinity")
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StoryboardValidationError(f"{path} keys must be strings")
            result[key] = _json_value(item, f"{path}.{key}")
        return result
    raise StoryboardValidationError(f"{path} must contain JSON-compatible values only")


def _metadata(value: Any, name: str = "metadata") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StoryboardValidationError(f"{name} must be an object")
    return _json_value(value, name)


def _unique_ids(values: Any, name: str) -> Tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise StoryboardValidationError(f"{name} must be a sequence of IDs")
    try:
        result = tuple(_identifier(item, f"{name}[]") for item in values)
    except TypeError:
        raise StoryboardValidationError(f"{name} must be a sequence of IDs") from None
    if len(set(result)) != len(result):
        raise StoryboardValidationError(f"{name} must not contain duplicates")
    return result


class TimingBasis(str, Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"


class ProposalReviewStatus(str, Enum):
    DRAFT = "draft"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"


class ContinuityKind(str, Enum):
    CHARACTER = "character"
    LOCATION = "location"
    PROP = "prop"


@dataclass(frozen=True)
class TimingInterval:
    """Half-open timeline interval in integer milliseconds, with explicit provenance."""

    start_ms: int
    end_ms: int
    basis: TimingBasis
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        for name in ("start_ms", "end_ms"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise StoryboardValidationError(f"timing.{name} must be a non-negative integer")
        if self.end_ms <= self.start_ms:
            raise StoryboardValidationError("timing.end_ms must be greater than start_ms")
        if not isinstance(self.basis, TimingBasis):
            raise StoryboardValidationError("timing.basis must be a TimingBasis")
        object.__setattr__(self, "metadata", _metadata(self.metadata, "timing.metadata"))

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def to_dict(self) -> dict[str, Any]:
        return {"start_ms": self.start_ms, "end_ms": self.end_ms,
                "basis": self.basis.value, "metadata": _metadata(self.metadata)}

    @classmethod
    def from_dict(cls, data: Any) -> "TimingInterval":
        if not isinstance(data, Mapping):
            raise StoryboardValidationError("timing must be an object")
        try:
            basis = TimingBasis(data.get("basis"))
        except (TypeError, ValueError):
            raise StoryboardValidationError("timing.basis is unsupported") from None
        return cls(data.get("start_ms"), data.get("end_ms"), basis,
                   data.get("metadata", {}))


@dataclass(frozen=True)
class NarrationTextUnit:
    """An exact slice of source text using zero-based, end-exclusive offsets."""

    unit_id: str
    start_offset: int
    end_offset: int
    timing: Optional[TimingInterval] = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.unit_id, "unit_id")
        for name in ("start_offset", "end_offset"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise StoryboardValidationError(f"{name} must be a non-negative integer")
        if self.end_offset <= self.start_offset:
            raise StoryboardValidationError("end_offset must be greater than start_offset")
        if self.timing is not None and not isinstance(self.timing, TimingInterval):
            raise StoryboardValidationError("unit.timing must be a TimingInterval or null")
        object.__setattr__(self, "metadata", _metadata(self.metadata, "unit.metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {"unit_id": self.unit_id, "start_offset": self.start_offset,
                "end_offset": self.end_offset,
                "timing": self.timing.to_dict() if self.timing else None,
                "metadata": _metadata(self.metadata)}

    @classmethod
    def from_dict(cls, data: Any) -> "NarrationTextUnit":
        if not isinstance(data, Mapping):
            raise StoryboardValidationError("narration text unit must be an object")
        timing = data.get("timing")
        return cls(data.get("unit_id"), data.get("start_offset"), data.get("end_offset"),
                   TimingInterval.from_dict(timing) if timing is not None else None,
                   data.get("metadata", {}))


@dataclass(frozen=True)
class NarrationSource:
    """Caller-supplied narration plus validated exact source slices."""

    source_id: str
    text: str
    units: Tuple[NarrationTextUnit, ...] = ()
    language: Optional[str] = None
    total_duration_ms: Optional[int] = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.source_id, "source_id")
        _text(self.text, "source.text", allow_empty=True)
        if self.language is not None:
            _text(self.language, "source.language")
        if self.total_duration_ms is not None and (
            isinstance(self.total_duration_ms, bool)
            or not isinstance(self.total_duration_ms, int)
            or self.total_duration_ms <= 0
        ):
            raise StoryboardValidationError("source.total_duration_ms must be a positive integer or null")
        units = tuple(self.units)
        if not all(isinstance(unit, NarrationTextUnit) for unit in units):
            raise StoryboardValidationError("source.units must contain NarrationTextUnit values")
        if len({unit.unit_id for unit in units}) != len(units):
            raise StoryboardValidationError("source unit IDs must be unique")
        previous_end = 0
        for unit in units:
            if unit.end_offset > len(self.text):
                raise StoryboardValidationError(f"unit {unit.unit_id} offsets exceed source text length")
            if unit.start_offset < previous_end:
                raise StoryboardValidationError("source text units must be ordered and non-overlapping")
            previous_end = unit.end_offset
        timed = [unit.timing for unit in units if unit.timing is not None]
        for previous, current in zip(timed, timed[1:]):
            if current.start_ms < previous.start_ms:
                raise StoryboardValidationError("measured/estimated unit timings must be ordered")
        if self.total_duration_ms is not None and any(
            timing.end_ms > self.total_duration_ms for timing in timed
        ):
            raise StoryboardValidationError("unit timing exceeds source total_duration_ms")
        object.__setattr__(self, "units", units)
        object.__setattr__(self, "metadata", _metadata(self.metadata, "source.metadata"))

    @property
    def source_fingerprint(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def text_for_unit(self, unit: NarrationTextUnit) -> str:
        if unit not in self.units:
            raise StoryboardValidationError("unit does not belong to this narration source")
        return self.text[unit.start_offset:unit.end_offset]

    def to_dict(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "text": self.text,
                "units": [unit.to_dict() for unit in self.units],
                "language": self.language, "total_duration_ms": self.total_duration_ms,
                "metadata": _metadata(self.metadata)}

    @classmethod
    def from_dict(cls, data: Any) -> "NarrationSource":
        if not isinstance(data, Mapping):
            raise StoryboardValidationError("narration source must be an object")
        units = data.get("units", [])
        if not isinstance(units, (list, tuple)):
            raise StoryboardValidationError("source.units must be a list")
        return cls(data.get("source_id"), data.get("text"), tuple(
            NarrationTextUnit.from_dict(item) for item in units
        ), data.get("language"), data.get("total_duration_ms"), data.get("metadata", {}))


@dataclass(frozen=True)
class ContinuityReference:
    """A stable descriptive reference, not a generated or verified asset."""

    reference_id: str
    kind: ContinuityKind
    description: str
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.reference_id, "reference_id")
        if not isinstance(self.kind, ContinuityKind):
            raise StoryboardValidationError("reference.kind must be a ContinuityKind")
        _text(self.description, "reference.description")
        object.__setattr__(self, "metadata", _metadata(self.metadata, "reference.metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {"reference_id": self.reference_id, "kind": self.kind.value,
                "description": self.description, "metadata": _metadata(self.metadata)}

    @classmethod
    def from_dict(cls, data: Any) -> "ContinuityReference":
        if not isinstance(data, Mapping):
            raise StoryboardValidationError("continuity reference must be an object")
        try:
            kind = ContinuityKind(data.get("kind"))
        except (TypeError, ValueError):
            raise StoryboardValidationError("reference.kind is unsupported") from None
        return cls(data.get("reference_id"), kind, data.get("description"),
                   data.get("metadata", {}))


@dataclass(frozen=True)
class StoryboardBeat:
    """One visual beat linked to one or more exact narration text units."""

    beat_id: str
    narration_unit_ids: Tuple[str, ...]
    visual_description: str
    timing: TimingInterval
    action_cues: Tuple[str, ...] = ()
    continuity_reference_ids: Tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        _identifier(self.beat_id, "beat_id")
        unit_ids = _unique_ids(self.narration_unit_ids, "beat.narration_unit_ids")
        if not unit_ids:
            raise StoryboardValidationError("beat.narration_unit_ids must not be empty")
        _text(self.visual_description, "beat.visual_description")
        if not isinstance(self.timing, TimingInterval):
            raise StoryboardValidationError("beat.timing must be a TimingInterval")
        cues = tuple(_text(item, "beat.action_cues[]") for item in self.action_cues)
        refs = _unique_ids(self.continuity_reference_ids, "beat.continuity_reference_ids")
        object.__setattr__(self, "narration_unit_ids", unit_ids)
        object.__setattr__(self, "action_cues", cues)
        object.__setattr__(self, "continuity_reference_ids", refs)
        object.__setattr__(self, "metadata", _metadata(self.metadata, "beat.metadata"))

    def to_dict(self) -> dict[str, Any]:
        return {"beat_id": self.beat_id, "narration_unit_ids": list(self.narration_unit_ids),
                "visual_description": self.visual_description, "timing": self.timing.to_dict(),
                "action_cues": list(self.action_cues),
                "continuity_reference_ids": list(self.continuity_reference_ids),
                "metadata": _metadata(self.metadata)}

    @classmethod
    def from_dict(cls, data: Any) -> "StoryboardBeat":
        if not isinstance(data, Mapping):
            raise StoryboardValidationError("storyboard beat must be an object")
        return cls(data.get("beat_id"), data.get("narration_unit_ids", []),
                   data.get("visual_description"), TimingInterval.from_dict(data.get("timing")),
                   tuple(data.get("action_cues", [])),
                   tuple(data.get("continuity_reference_ids", [])), data.get("metadata", {}))


@dataclass(frozen=True)
class StoryboardProposal:
    """Versioned, deterministic proposal envelope; approval is explicit input."""

    proposal_id: str
    source_id: str
    source_fingerprint: str
    beats: Tuple[StoryboardBeat, ...]
    review_status: ProposalReviewStatus = ProposalReviewStatus.DRAFT
    continuity_references: Tuple[ContinuityReference, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)
    proposal_version: int = STORYBOARD_PROPOSAL_VERSION

    def __post_init__(self) -> None:
        _identifier(self.proposal_id, "proposal_id")
        _identifier(self.source_id, "source_id")
        if not isinstance(self.source_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", self.source_fingerprint):
            raise StoryboardValidationError("proposal.source_fingerprint must be a SHA-256 hex digest")
        if isinstance(self.proposal_version, bool) or not isinstance(self.proposal_version, int) or self.proposal_version < 1:
            raise StoryboardValidationError("proposal_version must be a positive integer")
        if not isinstance(self.review_status, ProposalReviewStatus):
            raise StoryboardValidationError("review_status must be a ProposalReviewStatus")
        beats = tuple(self.beats)
        refs = tuple(self.continuity_references)
        if not all(isinstance(item, StoryboardBeat) for item in beats):
            raise StoryboardValidationError("proposal.beats must contain StoryboardBeat values")
        if not all(isinstance(item, ContinuityReference) for item in refs):
            raise StoryboardValidationError("proposal.continuity_references must contain ContinuityReference values")
        if len({item.beat_id for item in beats}) != len(beats):
            raise StoryboardValidationError("proposal beat IDs must be unique")
        if len({item.reference_id for item in refs}) != len(refs):
            raise StoryboardValidationError("proposal continuity reference IDs must be unique")
        unit_ids = [unit_id for beat in beats for unit_id in beat.narration_unit_ids]
        known_refs = {item.reference_id for item in refs}
        unknown_refs = sorted({ref for beat in beats for ref in beat.continuity_reference_ids} - known_refs)
        if unknown_refs:
            raise StoryboardValidationError(f"proposal contains unresolved continuity references: {', '.join(unknown_refs)}")
        for previous, current in zip(beats, beats[1:]):
            if current.timing.start_ms < previous.timing.start_ms:
                raise StoryboardValidationError("proposal beats must be ordered by start time")
        object.__setattr__(self, "beats", beats)
        object.__setattr__(self, "continuity_references", refs)
        object.__setattr__(self, "metadata", _metadata(self.metadata, "proposal.metadata"))

    def validate_against(self, source: NarrationSource) -> None:
        if not isinstance(source, NarrationSource):
            raise StoryboardValidationError("source must be a NarrationSource")
        if source.source_id != self.source_id or source.source_fingerprint != self.source_fingerprint:
            raise StoryboardValidationError("proposal source identity/fingerprint does not match narration source")
        known_units = {unit.unit_id for unit in source.units}
        unknown = sorted({unit_id for beat in self.beats for unit_id in beat.narration_unit_ids} - known_units)
        if unknown:
            raise StoryboardValidationError(f"proposal contains unknown narration units: {', '.join(unknown)}")

    def to_dict(self) -> dict[str, Any]:
        return {"proposal_version": self.proposal_version, "proposal_id": self.proposal_id,
                "source_id": self.source_id, "source_fingerprint": self.source_fingerprint,
                "review_status": self.review_status.value,
                "beats": [beat.to_dict() for beat in self.beats],
                "continuity_references": [ref.to_dict() for ref in self.continuity_references],
                "metadata": _metadata(self.metadata)}

    @classmethod
    def from_dict(cls, data: Any) -> "StoryboardProposal":
        if not isinstance(data, Mapping):
            raise StoryboardValidationError("storyboard proposal must be an object")
        version = data.get("proposal_version", STORYBOARD_PROPOSAL_VERSION)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise StoryboardValidationError("proposal_version must be a positive integer")
        if version > STORYBOARD_PROPOSAL_VERSION:
            raise StoryboardValidationError(f"unsupported future storyboard proposal version: {version}")
        beats, refs = data.get("beats", []), data.get("continuity_references", [])
        if not isinstance(beats, (list, tuple)) or not isinstance(refs, (list, tuple)):
            raise StoryboardValidationError("proposal beats and continuity_references must be lists")
        try:
            status = ProposalReviewStatus(data.get("review_status", ProposalReviewStatus.DRAFT.value))
        except (TypeError, ValueError):
            raise StoryboardValidationError("proposal.review_status is unsupported") from None
        return cls(data.get("proposal_id"), data.get("source_id"), data.get("source_fingerprint"),
                   tuple(StoryboardBeat.from_dict(item) for item in beats), status,
                   tuple(ContinuityReference.from_dict(item) for item in refs),
                   data.get("metadata", {}), version)
