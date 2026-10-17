from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union

from app.core.constants import DEFAULT_EXPLICIT_PAUSE_MS, NARRATION_MAX_CHUNK_CHARS
from app.text.chunker import chunk_text
from app.text.narration_parser import PauseItem, TextItem, parse_script


@dataclass(frozen=True)
class Chunk:
    id: str                       # e.g. scene_01_chunk_003
    text: str                     # exactly what is sent to the TTS provider
    style: Optional[str] = None   # metadata only; Edge TTS ignores styles


@dataclass(frozen=True)
class Silence:
    ms: int
    explicit: bool                # True = user-written [pause ...] marker


PlanItem = Union[Chunk, Silence]


@dataclass
class ScenePlan:
    scene_index: int
    items: List[PlanItem] = field(default_factory=list)
    style_tags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def chunks(self) -> List[Chunk]:
        return [i for i in self.items if isinstance(i, Chunk)]


def collapse_silences(items: List[PlanItem]) -> List[PlanItem]:
    """Merge neighbouring silences. An explicit [pause] replaces the automatic
    pause next to it (explicit pauses add up); otherwise the longer automatic
    pause wins. Trailing automatic silence is dropped -- the scene pause is
    applied between scenes during assembly."""
    merged: List[PlanItem] = []
    run: List[Silence] = []

    def flush() -> None:
        if not run:
            return
        explicit = [s.ms for s in run if s.explicit]
        if explicit:
            merged.append(Silence(sum(explicit), True))
        else:
            ms = max(s.ms for s in run)
            if ms > 0:
                merged.append(Silence(ms, False))
        run.clear()

    for item in items:
        if isinstance(item, Silence):
            run.append(item)
        else:
            flush()
            merged.append(item)
    flush()
    if merged and isinstance(merged[-1], Silence) and not merged[-1].explicit:
        merged.pop()
    return merged


def plan_scene(
    text: str,
    scene_index: int,
    *,
    sentence_pause_ms: int,
    paragraph_pause_ms: int,
    default_pause_ms: int = DEFAULT_EXPLICIT_PAUSE_MS,
    max_chars: int = NARRATION_MAX_CHUNK_CHARS,
) -> ScenePlan:
    """Turn scene text into an ordered list of speech chunks and silences.
    Pause markers and style tags never reach the provider: only Chunk.text is
    synthesized."""
    parsed = parse_script(text, default_pause_ms)
    plan = ScenePlan(scene_index=scene_index, style_tags=list(parsed.style_tags), warnings=list(parsed.warnings))
    per_sentence = sentence_pause_ms > 0
    counter = 0
    items: List[PlanItem] = []

    for paragraph in parsed.paragraphs:
        for item in paragraph.items:
            if isinstance(item, PauseItem):
                items.append(Silence(item.ms, True))
            elif isinstance(item, TextItem):
                for piece, ends_sentence in chunk_text(item.text, max_chars, per_sentence):
                    counter += 1
                    items.append(Chunk(f"scene_{scene_index:02d}_chunk_{counter:03d}", piece, item.style))
                    if per_sentence and ends_sentence:
                        items.append(Silence(sentence_pause_ms, False))
        items.append(Silence(paragraph_pause_ms, False))

    plan.items = collapse_silences(items)
    return plan