from __future__ import annotations

from app.core.timebase import seconds_to_ticks
from app.ui.studio_context import fmt_ticks, timeline_bounds


def test_ui_duration_formatter_uses_tick_rounding_not_float_seconds():
    assert fmt_ticks(seconds_to_ticks("59.49")) == "00:59"
    assert fmt_ticks(seconds_to_ticks("59.5")) == "01:00"
    assert fmt_ticks(seconds_to_ticks("3661.5")) == "61:02"


def test_timeline_canvas_bounds_are_derived_from_integer_tick_boundaries():
    total = seconds_to_ticks("3")
    assert timeline_bounds(0, seconds_to_ticks("1"), total, 900) == (0.0, 300.0)
    assert timeline_bounds(seconds_to_ticks("1"), seconds_to_ticks("1"), total, 900) == (300.0, 600.0)


def test_timeline_canvas_mapping_handles_ticks_above_javascript_safe_integer():
    total = 10**20
    start = 25 * 10**18
    slot = 25 * 10**18
    assert timeline_bounds(start, slot, total, 800) == (200.0, 400.0)


def test_timeline_canvas_bounds_for_invalid_total_are_safe():
    assert timeline_bounds(0, 10, 0, 900) == (0.0, 0.0)
