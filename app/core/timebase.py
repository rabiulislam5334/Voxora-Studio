"""Exact integer timebase utilities for Voxora Studio.

The canonical clock is 141,120,000 ticks per second.  Conversion helpers
accept rational inputs and make rounding explicit at every non-integral
boundary.  Python integers are intentionally unbounded; serialize tick
counts as decimal strings when crossing JSON/JavaScript boundaries.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, ROUND_DOWN
from fractions import Fraction
from typing import TypeAlias

TICKS_PER_SECOND = 141_120_000
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991

RoundingMode: TypeAlias = str
TimeValue: TypeAlias = int | float | str | Decimal | Fraction

_ROUNDING_MODES = {
    "half_up": ROUND_HALF_UP,
    "floor": ROUND_FLOOR,
    "ceil": ROUND_CEILING,
    "trunc": ROUND_DOWN,
}


class TimebaseError(ValueError):
    """Base exception for invalid timebase values."""


class TimebaseRangeError(TimebaseError):
    """Raised when a value is outside the supported non-negative domain."""


def _require_non_negative_int(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer (bool is not accepted)")
    if value < 0:
        raise TimebaseRangeError(f"{name} must be non-negative")
    return value


def _as_fraction(value: TimeValue, name: str) -> Fraction:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a numeric time value")
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise TimebaseError(f"{name} must be finite")
        result = Fraction(value)
    elif isinstance(value, int):
        result = Fraction(value, 1)
    elif isinstance(value, float):
        if not value == value or value in (float("inf"), float("-inf")):
            raise TimebaseError(f"{name} must be finite")
        # str() avoids importing the float's full binary approximation.
        result = Fraction(Decimal(str(value)))
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value.strip())
        except (InvalidOperation, ValueError) as exc:
            raise TimebaseError(f"{name} must be a valid decimal string") from exc
        if not decimal_value.is_finite():
            raise TimebaseError(f"{name} must be finite")
        result = Fraction(decimal_value)
    else:
        raise TypeError(f"{name} must be int, float, str, Decimal, or Fraction")
    if result < 0:
        raise TimebaseRangeError(f"{name} must be non-negative")
    return result


def _round_fraction(value: Fraction, rounding: RoundingMode) -> int:
    """Round a non-negative fraction to an integer using a named policy."""
    if rounding not in _ROUNDING_MODES:
        choices = ", ".join(sorted(_ROUNDING_MODES))
        raise TimebaseError(f"rounding must be one of: {choices}")
    numerator, denominator = value.numerator, value.denominator
    if rounding == "exact":
        quotient, remainder = divmod(numerator, denominator)
        if remainder:
            raise TimebaseError("conversion is not exact with the selected timebase")
        return quotient
    decimal_value = Decimal(numerator) / Decimal(denominator)
    return int(decimal_value.to_integral_value(rounding=_ROUNDING_MODES[rounding]))


def seconds_to_ticks(seconds: TimeValue, *, rounding: RoundingMode = "half_up") -> int:
    """Convert seconds to canonical ticks.

    Decimal strings and Decimal/Fraction inputs are recommended for values
    that must be reproducible. Float inputs are interpreted via str(float).
    """
    return _round_fraction(_as_fraction(seconds, "seconds") * TICKS_PER_SECOND, rounding)


def ticks_to_seconds(ticks: int) -> Decimal:
    """Return seconds as Decimal; no float conversion is performed."""
    ticks = _require_non_negative_int(ticks, "ticks")
    return Decimal(ticks) / Decimal(TICKS_PER_SECOND)


def samples_to_ticks(
    samples: int, sample_rate: int, *, rounding: RoundingMode = "exact"
) -> int:
    """Convert a sample count to ticks at an integer samples-per-second rate."""
    samples = _require_non_negative_int(samples, "samples")
    sample_rate = _require_non_negative_int(sample_rate, "sample_rate")
    if sample_rate == 0:
        raise TimebaseRangeError("sample_rate must be greater than zero")
    return _round_fraction(Fraction(samples * TICKS_PER_SECOND, sample_rate), rounding)


def ticks_to_samples(
    ticks: int, sample_rate: int, *, rounding: RoundingMode = "half_up"
) -> int:
    """Convert ticks to a sample count at an integer samples-per-second rate."""
    ticks = _require_non_negative_int(ticks, "ticks")
    sample_rate = _require_non_negative_int(sample_rate, "sample_rate")
    if sample_rate == 0:
        raise TimebaseRangeError("sample_rate must be greater than zero")
    return _round_fraction(Fraction(ticks * sample_rate, TICKS_PER_SECOND), rounding)


def _validate_fps(fps_num: int, fps_den: int) -> tuple[int, int]:
    fps_num = _require_non_negative_int(fps_num, "fps_num")
    fps_den = _require_non_negative_int(fps_den, "fps_den")
    if fps_num == 0 or fps_den == 0:
        raise TimebaseRangeError("fps_num and fps_den must be greater than zero")
    return fps_num, fps_den


def frames_to_ticks(
    frames: int,
    fps_num: int,
    fps_den: int = 1,
    *,
    rounding: RoundingMode = "exact",
) -> int:
    """Convert a frame count using rational FPS (fps_num / fps_den)."""
    frames = _require_non_negative_int(frames, "frames")
    fps_num, fps_den = _validate_fps(fps_num, fps_den)
    return _round_fraction(
        Fraction(frames * TICKS_PER_SECOND * fps_den, fps_num), rounding
    )


def ticks_to_frames(
    ticks: int,
    fps_num: int,
    fps_den: int = 1,
    *,
    rounding: RoundingMode = "half_up",
) -> int:
    """Convert ticks to frames using rational FPS (fps_num / fps_den)."""
    ticks = _require_non_negative_int(ticks, "ticks")
    fps_num, fps_den = _validate_fps(fps_num, fps_den)
    return _round_fraction(
        Fraction(ticks * fps_num, TICKS_PER_SECOND * fps_den), rounding
    )


def rescale_ticks(
    ticks: int,
    source_ticks_per_second: int,
    target_ticks_per_second: int,
    *,
    rounding: RoundingMode = "half_up",
) -> int:
    """Rescale a non-negative tick count between integer timebases."""
    ticks = _require_non_negative_int(ticks, "ticks")
    source = _require_non_negative_int(source_ticks_per_second, "source_ticks_per_second")
    target = _require_non_negative_int(target_ticks_per_second, "target_ticks_per_second")
    if source == 0 or target == 0:
        raise TimebaseRangeError("source and target timebases must be greater than zero")
    return _round_fraction(Fraction(ticks * target, source), rounding)


def serialize_ticks(ticks: int) -> str:
    """Serialize ticks as a decimal string safe for JSON/JavaScript transport."""
    return str(_require_non_negative_int(ticks, "ticks"))


def deserialize_ticks(value: str | int) -> int:
    """Parse a decimal tick string (or a Python integer) without precision loss."""
    if isinstance(value, bool):
        raise TypeError("ticks must be a decimal string or integer")
    if isinstance(value, int):
        return _require_non_negative_int(value, "ticks")
    if not isinstance(value, str) or not value or value.strip() != value:
        raise TimebaseError("ticks must be a non-empty decimal integer string")
    if not value.isascii() or not value.isdecimal():
        raise TimebaseError("ticks must contain decimal digits only")
    return int(value)


def is_json_safe_integer(value: int) -> bool:
    """Whether an integer is exactly representable by JavaScript Number."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("value must be an integer (bool is not accepted)")
    return -MAX_SAFE_JSON_INTEGER <= value <= MAX_SAFE_JSON_INTEGER
