from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Union

from app.core.constants import (
    DEFAULT_EXPLICIT_PAUSE_MS,
    MAX_EXPLICIT_PAUSE_MS,
    RECOGNIZED_STYLE_TAGS,
)

# [pause], [pause 500ms], [pause 1s], [pause 1.5s]. Anything that starts with
# "[pause" is treated as a pause marker and is NEVER spoken -- if its argument
# is malformed it is dropped with a warning instead of being read aloud.
_MARKER_RE = re.compile(
    r"\[\s*(?:pause\b(?P<pause_args>[^\]]*)|(?P<style>"
    + "|".join(re.escape(t) for t in RECOGNIZED_STYLE_TAGS)
    + r")\s*)\]",
    re.IGNORECASE,
)
_PAUSE_ARG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s)", re.IGNORECASE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n[ \t]*\n+")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class TextItem:
    text: str
    style: Optional[str] = None  # last style tag seen; metadata only


@dataclass(frozen=True)
class PauseItem:
    ms: int


@dataclass
class Paragraph:
    items: List[Union[TextItem, PauseItem]] = field(default_factory=list)


@dataclass
class ParsedScript:
    paragraphs: List[Paragraph] = field(default_factory=list)
    style_tags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _parse_pause_ms(args: str, default_ms: int, warnings: List[str]) -> Optional[int]:
    cleaned = args.strip()
    if not cleaned:
        return default_ms
    match = _PAUSE_ARG_RE.fullmatch(cleaned)
    if match is None:
        warnings.append(f'Ignored invalid pause marker "[pause {cleaned}]" (use e.g. [pause 500ms], [pause 1s], [pause 1.5s]).')
        return None
    value = float(match.group(1))
    ms = round(value if match.group(2).lower() == "ms" else value * 1000)
    if ms > MAX_EXPLICIT_PAUSE_MS:
        warnings.append(f'Pause "[pause {cleaned}]" was shortened to {MAX_EXPLICIT_PAUSE_MS // 1000} seconds.')
        ms = MAX_EXPLICIT_PAUSE_MS
    return ms


def parse_script(text: str, default_pause_ms: int = DEFAULT_EXPLICIT_PAUSE_MS) -> ParsedScript:
    """Split scene text into paragraphs (blank-line separated) made of text
    and explicit-pause items. The ORIGINAL text is never modified -- this
    builds a separate spoken-text view. Single line breaks inside a
    paragraph are treated as spaces. Recognised style tags are removed from
    the spoken text and remembered as sticky per-item metadata."""
    result = ParsedScript()
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    current_style: Optional[str] = None

    for raw_paragraph in _PARAGRAPH_SPLIT_RE.split(normalized):
        paragraph = Paragraph()
        position = 0

        def add_text(segment: str) -> None:
            cleaned = _WS_RE.sub(" ", segment).strip()
            if cleaned:
                paragraph.items.append(TextItem(cleaned, current_style))

        for match in _MARKER_RE.finditer(raw_paragraph):
            add_text(raw_paragraph[position:match.start()])
            position = match.end()
            style = match.group("style")
            if style:
                current_style = style.lower()
                if current_style not in result.style_tags:
                    result.style_tags.append(current_style)
                continue
            ms = _parse_pause_ms(match.group("pause_args") or "", default_pause_ms, result.warnings)
            if ms:
                paragraph.items.append(PauseItem(ms))
        add_text(raw_paragraph[position:])

        if paragraph.items:
            result.paragraphs.append(paragraph)
    return result