from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

MIN_SLOT_S = 0.5
FINAL_TAIL_PAD_S = 0.5


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


@dataclass(frozen=True)
class VideoTimeline:
    slots: List[SceneSlot]
    total_s: float
    transition_s: float   # effective crossfade length (0 for cuts)


def compute_timeline(
    inputs: Sequence[SceneTimingInput],
    *,
    transition: str,
    transition_s: float,
    default_duration_s: float,
) -> VideoTimeline:
    """Lay scenes out on one timeline.

    * With narration, a scene's slot is at least narration + the scene pause
      (the last scene gets a short tail), so speech is NEVER cut off; if the
      user configured a longer duration, that wins.
    * Without narration, the slot is the configured duration or the default.
    * A crossfade overlaps the end of a scene with the start of the next one
      by `transition_s`; that overlap is extra video length at the end of each
      segment, so the slot boundaries (and the narration) never move.
    """
    n = len(inputs)
    raw_slots: List[float] = []
    extended: List[bool] = []
    for index, item in enumerate(inputs):
        configured = item.configured_s
        if item.narration_s is not None:
            tail = item.pause_s if index < n - 1 else max(item.pause_s, FINAL_TAIL_PAD_S)
            needed = item.narration_s + tail
            slot = max(configured or 0.0, needed)
            extended.append(configured is not None and needed > configured + 1e-9)
        else:
            slot = configured if configured is not None else default_duration_s
            extended.append(False)
        raw_slots.append(max(MIN_SLOT_S, slot))

    overlap = 0.0
    if transition == "crossfade" and n > 1:
        overlap = max(0.0, min(transition_s, 0.5 * min(raw_slots)))

    slots: List[SceneSlot] = []
    cursor = 0.0
    for index, item in enumerate(inputs):
        slot = raw_slots[index]
        segment = slot + (overlap if index < n - 1 else 0.0)
        slots.append(SceneSlot(item.scene_id, cursor, slot, segment, item.narration_s, extended[index]))
        cursor += slot
    return VideoTimeline(slots=slots, total_s=cursor, transition_s=overlap)