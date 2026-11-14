from __future__ import annotations

import pytest

from app.core.timebase import seconds_to_ticks
from app.studio.timing import SceneTimingInput, compute_timeline


def test_timeline_exposes_integer_tick_values_and_legacy_seconds():
    timeline = compute_timeline(
        [
            SceneTimingInput("intro", 4.0, None, 1.0),
            SceneTimingInput("body", 2.0, None, 1.0),
        ],
        transition="cut",
        transition_s=0.5,
        default_duration_s=5.0,
    )

    assert [slot.slot_ticks for slot in timeline.slots] == [
        seconds_to_ticks(5), seconds_to_ticks(3)
    ]
    assert [slot.start_ticks for slot in timeline.slots] == [
        0, seconds_to_ticks(5)
    ]
    assert timeline.total_ticks == seconds_to_ticks(8)
    assert timeline.transition_ticks == 0

    # Existing seconds-facing API remains available and unchanged.
    assert [slot.slot_s for slot in timeline.slots] == [5.0, 3.0]
    assert [slot.start_s for slot in timeline.slots] == [0.0, 5.0]
    assert timeline.total_s == 8.0
    assert timeline.transition_s == 0.0


def test_crossfade_overlap_and_segment_lengths_are_tick_exact():
    timeline = compute_timeline(
        [SceneTimingInput(scene_id, 3.0, None, 1.0) for scene_id in "abc"],
        transition="crossfade",
        transition_s=0.5,
        default_duration_s=5.0,
    )
    slot_ticks = seconds_to_ticks(4)
    overlap_ticks = seconds_to_ticks("0.5")

    assert timeline.transition_ticks == overlap_ticks
    assert [slot.start_ticks for slot in timeline.slots] == [
        0, slot_ticks, slot_ticks * 2
    ]
    assert [slot.segment_ticks for slot in timeline.slots] == [
        slot_ticks + overlap_ticks,
        slot_ticks + overlap_ticks,
        slot_ticks,
    ]
    assert timeline.total_ticks == slot_ticks * 3


def test_crossfade_limit_uses_integer_half_of_shortest_slot():
    timeline = compute_timeline(
        [
            SceneTimingInput("short", None, 0.6),
            SceneTimingInput("long", None, 4.0),
        ],
        transition="crossfade",
        transition_s=2.0,
        default_duration_s=5.0,
    )
    expected = seconds_to_ticks("0.6") // 2
    assert timeline.transition_ticks == expected
    assert timeline.transition_s == pytest.approx(0.3)


def test_long_timeline_cursor_has_no_float_accumulation():
    count = 10_000
    # Scene slots have a deliberate 0.5 s minimum; use 0.6 s to
    # exercise repeated cursor accumulation without triggering that clamp.
    duration_ticks = seconds_to_ticks("0.6")
    timeline = compute_timeline(
        [SceneTimingInput(str(i), None, 0.6) for i in range(count)],
        transition="cut",
        transition_s=0.0,
        default_duration_s=5.0,
    )

    assert timeline.total_ticks == count * duration_ticks
    assert timeline.slots[-1].start_ticks == (count - 1) * duration_ticks
    assert timeline.slots[-1].start_ticks + timeline.slots[-1].slot_ticks == timeline.total_ticks


def test_narration_extension_comparison_uses_ticks_not_float_epsilon():
    timeline = compute_timeline(
        [SceneTimingInput("scene", 1.000001, 1.0, 0.0)],
        transition="cut",
        transition_s=0.0,
        default_duration_s=5.0,
    )
    slot = timeline.slots[0]

    assert slot.extended is True
    assert slot.slot_ticks == seconds_to_ticks("1.500001")
    assert slot.narration_ticks == seconds_to_ticks("1.000001")


def test_empty_timeline_has_zero_tick_totals():
    timeline = compute_timeline(
        [],
        transition="crossfade",
        transition_s=0.5,
        default_duration_s=5.0,
    )
    assert timeline.slots == []
    assert timeline.total_ticks == 0
    assert timeline.transition_ticks == 0
    assert timeline.total_s == 0.0
