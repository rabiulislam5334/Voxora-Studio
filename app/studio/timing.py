from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.core.timebase import seconds_to_ticks, ticks_to_seconds

MIN_SLOT_S = 0.5
FINAL_TAIL_PAD_S = 0.5


def _seconds_to_ticks(value: float) -> int:
    """Convert a public seconds value at the timing API boundary."""
    return seconds_to_ticks(value, rounding="half_up")


def _ticks_to_seconds_float(value: int) -> float:
    """Preserve the existing seconds-facing API for downstream callers."""
    return float(ticks_to_seconds(value))


@dataclass(frozen=True)
class SceneTimingInput:
    scene_id: str
    narration_s: Optional[float]   # actual narration duration, None if not narrated
    configured_s: Optional[float]  # user's duration for the scene, None = automatic
    pause_s: float = 0.0           # silence that follows the narration (scene pause)


@dataclass(frozen=True)
class SceneSlot:
    scene_id: str
    start_s: float        # where this scene begins on the final timeline
    slot_s: float         # time reserved for this scene (narration + pause, or configured)
    segment_s: float      # length of the rendered video segment (slot + crossfade overlap)
    narration_s: Optional[float]
    extended: bool        # True when narration forced the slot longer than the configured duration
    # Canonical values. Seconds fields above remain for backward compatibility.
    start_ticks: int = 0
    slot_ticks: int = 0
    segment_ticks: int = 0
    narration_ticks: Optional[int] = None


@dataclass(frozen=True)
class VideoTimeline:
    slots: List[SceneSlot]
    total_s: float
    transition_s: float   # effective crossfade length (0 for cuts)
    # Canonical values. Seconds fields above remain for backward compatibility.
    total_ticks: int = 0
    transition_ticks: int = 0


def compute_timeline(
    inputs: Sequence[SceneTimingInput],
    *,
    transition: str,
    transition_s: float,
    default_duration_s: float,
) -> VideoTimeline:
    """Lay scenes out using integer ticks as the authoritative timebase.

    Seconds are accepted at this public compatibility boundary and converted
    once. Slot boundaries, overlap limits, and the running cursor are all
    calculated with integers; seconds are derived only for the legacy result
    fields consumed by existing callers.

    * With narration, a scene's slot is at least narration + the scene pause
      (the last scene gets a short tail), so speech is NEVER cut off; if the
      user configured a longer duration, that wins.
    * Without narration, the slot is the configured duration or the default.
    * A crossfade overlaps the end of a scene with the start of the next one
      by the effective transition length; slot boundaries never move.
    """
    n = len(inputs)
    min_slot_ticks = _seconds_to_ticks(MIN_SLOT_S)
    final_tail_pad_ticks = _seconds_to_ticks(FINAL_TAIL_PAD_S)

    raw_slots: List[int] = []
    narration_values: List[Optional[int]] = []
    extended: List[bool] = []

    for index, item in enumerate(inputs):
        narration_ticks = (
            _seconds_to_ticks(item.narration_s)
            if item.narration_s is not None else None
        )
        narration_values.append(narration_ticks)

        configured_ticks = (
            _seconds_to_ticks(item.configured_s)
            if item.configured_s is not None else None
        )

        if narration_ticks is not None:
            pause_ticks = _seconds_to_ticks(item.pause_s)
            tail_ticks = (
                pause_ticks
                if index < n - 1
                else max(pause_ticks, final_tail_pad_ticks)
            )
            needed_ticks = narration_ticks + tail_ticks
            slot_ticks = max(configured_ticks or 0, needed_ticks)
            extended.append(
                configured_ticks is not None and needed_ticks > configured_ticks
            )
        else:
            if configured_ticks is not None:
                slot_ticks = configured_ticks
            else:
                slot_ticks = _seconds_to_ticks(default_duration_s)
            extended.append(False)

        raw_slots.append(max(min_slot_ticks, slot_ticks))

    overlap_ticks = 0
    if transition == "crossfade" and n > 1:
        requested_overlap_ticks = _seconds_to_ticks(max(0.0, transition_s))
        overlap_ticks = min(requested_overlap_ticks, min(raw_slots) // 2)

    slots: List[SceneSlot] = []
    cursor_ticks = 0
    for index, item in enumerate(inputs):
        slot_ticks = raw_slots[index]
        segment_ticks = slot_ticks + (
            overlap_ticks if index < n - 1 else 0
        )
        narration_ticks = narration_values[index]
        slots.append(
            SceneSlot(
                scene_id=item.scene_id,
                start_s=_ticks_to_seconds_float(cursor_ticks),
                slot_s=_ticks_to_seconds_float(slot_ticks),
                segment_s=_ticks_to_seconds_float(segment_ticks),
                narration_s=(
                    _ticks_to_seconds_float(narration_ticks)
                    if narration_ticks is not None else None
                ),
                extended=extended[index],
                start_ticks=cursor_ticks,
                slot_ticks=slot_ticks,
                segment_ticks=segment_ticks,
                narration_ticks=narration_ticks,
            )
        )
        cursor_ticks += slot_ticks

    return VideoTimeline(
        slots=slots,
        total_s=_ticks_to_seconds_float(cursor_ticks),
        transition_s=_ticks_to_seconds_float(overlap_ticks),
        total_ticks=cursor_ticks,
        transition_ticks=overlap_ticks,
    )
