"""Validated, deterministic transition specifications for scene compositing.

This module is renderer-independent. It defines transition intent and frame
progress without opening images, invoking FFmpeg, or mutating project state.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

TRANSITION_SPEC_VERSION = 1
TRANSITION_EFFECTS = (
    "cut",
    "crossfade",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
    "dip_to_color",
)
TRANSITION_EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out")
_DIRECTIONAL_WIPES = frozenset({
    "wipe_left", "wipe_right", "wipe_up", "wipe_down",
})


class TransitionValidationError(ValueError):
    """Raised when a transition specification or frame interval is invalid."""


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TransitionValidationError(f"{name} must be an integer >= {minimum}")
    return value


def _eased(progress: float, easing: str) -> float:
    if easing == "linear":
        return progress
    if easing == "ease_in":
        return progress * progress
    if easing == "ease_out":
        return 1.0 - (1.0 - progress) ** 2
    if easing == "ease_in_out":
        return progress * progress * (3.0 - 2.0 * progress)
    raise TransitionValidationError(f"unsupported transition easing: {easing!r}")


@dataclass(frozen=True)
class TransitionSpec:
    """Immutable transition configuration; duration is canonical project ticks."""

    effect: str
    duration_ticks: int
    easing: str = "linear"
    color_rgb: Optional[Tuple[int, int, int]] = None
    version: int = TRANSITION_SPEC_VERSION
    extra: Mapping[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if self.effect not in TRANSITION_EFFECTS:
            raise TransitionValidationError(
                f"unsupported transition effect: {self.effect!r}"
            )
        duration = _integer(self.duration_ticks, "duration_ticks")
        if self.effect == "cut":
            if duration != 0:
                raise TransitionValidationError("cut transitions must have zero duration")
        elif duration <= 0:
            raise TransitionValidationError(
                f"{self.effect} transitions require a positive duration"
            )
        if self.easing not in TRANSITION_EASINGS:
            raise TransitionValidationError(
                "easing must be linear, ease_in, ease_out, or ease_in_out"
            )
        if self.effect == "dip_to_color":
            if not isinstance(self.color_rgb, (tuple, list)) or len(self.color_rgb) != 3:
                raise TransitionValidationError(
                    "dip_to_color requires an RGB color with three integer channels"
                )
            color = tuple(
                _integer(channel, "color_rgb channel")
                for channel in self.color_rgb
            )
            if any(channel > 255 for channel in color):
                raise TransitionValidationError("RGB color channels must be between 0 and 255")
            object.__setattr__(self, "color_rgb", color)
        elif self.color_rgb is not None:
            raise TransitionValidationError(
                "color_rgb is only valid for dip_to_color transitions"
            )
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version != TRANSITION_SPEC_VERSION:
            raise TransitionValidationError("unsupported transition specification version")
        if not isinstance(self.extra, Mapping):
            raise TransitionValidationError("transition extra must be an object")
        object.__setattr__(self, "extra", copy.deepcopy(dict(self.extra)))

    @classmethod
    def cut(cls) -> "TransitionSpec":
        return cls(effect="cut", duration_ticks=0)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "version": self.version,
            "effect": self.effect,
            "duration_ticks": self.duration_ticks,
            "easing": self.easing,
        }
        if self.color_rgb is not None:
            result["color_rgb"] = list(self.color_rgb)
        for key, value in self.extra.items():
            if key not in result:
                result[key] = copy.deepcopy(value)
        return result

    @classmethod
    def from_dict(cls, data: Any) -> "TransitionSpec":
        if not isinstance(data, Mapping):
            raise TransitionValidationError("transition specification must be an object")
        version = data.get("version", TRANSITION_SPEC_VERSION)
        known = {"version", "effect", "duration_ticks", "easing", "color_rgb"}
        color = data.get("color_rgb")
        if isinstance(color, list):
            color = tuple(color)
        return cls(
            effect=data.get("effect"),
            duration_ticks=data.get("duration_ticks"),
            easing=data.get("easing", "linear"),
            color_rgb=color,
            version=version,
            extra={key: copy.deepcopy(value) for key, value in data.items() if key not in known},
        )

    @property
    def fingerprint(self) -> str:
        try:
            payload = json.dumps(
                self.to_dict(), ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TransitionValidationError(
                f"transition metadata cannot be fingerprinted safely: {exc}"
            ) from exc
        return hashlib.sha256(payload).hexdigest()


def transition_progress(
    frame_index: int,
    frame_count: int,
    *,
    easing: str = "linear",
) -> float:
    """Return deterministic normalized progress for a transition frame.

    The first frame is exactly 0 and the final frame exactly 1. At least two
    frames are required so both endpoints can be represented.
    """
    count = _integer(frame_count, "frame_count", minimum=2)
    index = _integer(frame_index, "frame_index")
    if index >= count:
        raise TransitionValidationError("frame_index must be less than frame_count")
    if easing not in TRANSITION_EASINGS:
        raise TransitionValidationError(
            "easing must be linear, ease_in, ease_out, or ease_in_out"
        )
    if index == 0:
        return 0.0
    if index == count - 1:
        return 1.0
    return _eased(index / (count - 1), easing)


def transition_boundary(length: int, progress: float) -> int:
    """Map normalized progress to a pixel boundary using round-half-up."""
    size = _integer(length, "length", minimum=1)
    if isinstance(progress, bool) or not isinstance(progress, (int, float)):
        raise TransitionValidationError("progress must be a finite number between 0 and 1")
    value = float(progress)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise TransitionValidationError("progress must be a finite number between 0 and 1")
    return max(0, min(size, math.floor(size * value + 0.5)))


__all__ = [
    "TRANSITION_SPEC_VERSION",
    "TRANSITION_EFFECTS",
    "TRANSITION_EASINGS",
    "TransitionSpec",
    "TransitionValidationError",
    "transition_progress",
    "transition_boundary",
]
