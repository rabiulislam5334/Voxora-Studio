from decimal import Decimal
from fractions import Fraction

import pytest

from app.core.timebase import (
    MAX_SAFE_JSON_INTEGER,
    TICKS_PER_SECOND,
    TimebaseError,
    TimebaseRangeError,
    deserialize_ticks,
    frames_to_ticks,
    is_json_safe_integer,
    samples_to_ticks,
    seconds_to_ticks,
    serialize_ticks,
    ticks_to_frames,
    ticks_to_samples,
    ticks_to_seconds,
)


def test_canonical_timebase_constant():
    assert TICKS_PER_SECOND == 141_120_000


@pytest.mark.parametrize(
    ("sample_rate", "ticks_per_sample"),
    [
        (32_000, 4_410),
        (44_100, 3_200),
        (48_000, 2_940),
        (88_200, 1_600),
        (96_000, 1_470),
        (192_000, 735),
    ],
)
def test_common_audio_sample_rates_are_exact(sample_rate, ticks_per_sample):
    assert samples_to_ticks(1, sample_rate) == ticks_per_sample
    assert samples_to_ticks(123_456, sample_rate) == 123_456 * ticks_per_sample
    assert ticks_to_samples(123_456 * ticks_per_sample, sample_rate, rounding="exact") == 123_456


@pytest.mark.parametrize(
    ("fps_num", "fps_den", "ticks_per_frame"),
    [
        (24, 1, 5_880_000),
        (25, 1, 5_644_800),
        (30, 1, 4_704_000),
        (24_000, 1_001, 5_885_880),
        (30_000, 1_001, 4_708_704),
        (60_000, 1_001, 2_354_352),
    ],
)
def test_common_frame_rates_are_exact(fps_num, fps_den, ticks_per_frame):
    assert frames_to_ticks(1, fps_num, fps_den) == ticks_per_frame
    assert frames_to_ticks(10_000, fps_num, fps_den) == 10_000 * ticks_per_frame
    assert ticks_to_frames(10_000 * ticks_per_frame, fps_num, fps_den, rounding="exact") == 10_000


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", TICKS_PER_SECOND),
        ("0.5", TICKS_PER_SECOND // 2),
        (Decimal("1.25"), TICKS_PER_SECOND * 5 // 4),
        (Fraction(1, 3), TICKS_PER_SECOND // 3),
        (0.1, 14_112_000),
    ],
)
def test_seconds_to_ticks_uses_exact_decimal_or_rational_input(value, expected):
    assert seconds_to_ticks(value) == expected


def test_seconds_round_trip_as_decimal():
    assert ticks_to_seconds(TICKS_PER_SECOND * 90) == Decimal("90")


def test_24_hour_timeline_has_no_frame_or_sample_drift():
    day_ticks = seconds_to_ticks("86400")
    assert day_ticks == 12_193_920_000_000
    assert ticks_to_samples(day_ticks, 48_000, rounding="exact") == 4_147_200_000
    assert ticks_to_frames(day_ticks, 30, rounding="exact") == 2_592_000


def test_half_up_rounding_is_deterministic():
    assert seconds_to_ticks(Fraction(1, 2 * TICKS_PER_SECOND)) == 1
    assert seconds_to_ticks(Fraction(1, 3 * TICKS_PER_SECOND)) == 0
    assert seconds_to_ticks(Fraction(1, 3 * TICKS_PER_SECOND), rounding="ceil") == 1
    assert seconds_to_ticks(Fraction(1, 3 * TICKS_PER_SECOND), rounding="floor") == 0


def test_exact_rounding_rejects_non_integral_conversion():
    with pytest.raises(TimebaseError):
        samples_to_ticks(1, 44_117, rounding="exact")


def test_non_exact_tick_to_sample_conversion_can_choose_rounding():
    assert ticks_to_samples(1, 48_000, rounding="floor") == 0
    assert ticks_to_samples(1, 48_000, rounding="ceil") == 1


def test_large_tick_values_do_not_overflow_python_integer_arithmetic():
    huge = 10**40
    assert ticks_to_samples(huge, 48_000) >= 0
    assert deserialize_ticks(serialize_ticks(huge)) == huge


@pytest.mark.parametrize("bad_value", [-1, True, 1.0, "1"])
def test_sample_count_requires_non_negative_integer(bad_value):
    with pytest.raises((TypeError, TimebaseRangeError)):
        samples_to_ticks(bad_value, 48_000)


@pytest.mark.parametrize("bad_rate", [0, -1, True, 48_000.0])
def test_sample_rate_must_be_positive_integer(bad_rate):
    with pytest.raises((TypeError, TimebaseRangeError)):
        samples_to_ticks(1, bad_rate)


@pytest.mark.parametrize("bad_fps", [0, -1, True, 30.0])
def test_fps_numerator_must_be_positive_integer(bad_fps):
    with pytest.raises((TypeError, TimebaseRangeError)):
        frames_to_ticks(1, bad_fps)


def test_fps_denominator_must_be_positive():
    with pytest.raises(TimebaseRangeError):
        frames_to_ticks(1, 30, 0)


@pytest.mark.parametrize("bad_seconds", [-0.1, float("nan"), float("inf"), "NaN", True, "not-a-number"])
def test_seconds_reject_negative_non_finite_and_invalid_values(bad_seconds):
    with pytest.raises((TypeError, TimebaseError, TimebaseRangeError)):
        seconds_to_ticks(bad_seconds)


def test_negative_ticks_are_rejected():
    with pytest.raises(TimebaseRangeError):
        ticks_to_seconds(-1)


@pytest.mark.parametrize("bad_rounding", ["nearest", "bankers", None])
def test_unknown_rounding_mode_is_rejected(bad_rounding):
    with pytest.raises(TimebaseError):
        seconds_to_ticks("1", rounding=bad_rounding)


def test_tick_serialization_preserves_large_values_as_decimal_strings():
    value = 9_007_199_254_740_992
    assert serialize_ticks(value) == "9007199254740992"
    assert deserialize_ticks("9007199254740992") == value
    assert deserialize_ticks(value) == value


@pytest.mark.parametrize("bad_serialized", ["", " 1", "1 ", "-1", "+1", "1.0", "١"])
def test_tick_deserialization_rejects_non_canonical_decimal_strings(bad_serialized):
    with pytest.raises(TimebaseError):
        deserialize_ticks(bad_serialized)


def test_javascript_safe_integer_boundary():
    assert is_json_safe_integer(MAX_SAFE_JSON_INTEGER)
    assert is_json_safe_integer(-MAX_SAFE_JSON_INTEGER)
    assert not is_json_safe_integer(MAX_SAFE_JSON_INTEGER + 1)
    with pytest.raises(TypeError):
        is_json_safe_integer(True)
