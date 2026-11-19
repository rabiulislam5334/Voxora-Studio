"""Voxora-to-Cinematic-Skill narration timing bridge.

Unlike the upstream default Doc.W implementation, this bridge never estimates
word positions from character counts. It requires actual word timestamps from a
trusted alignment source, keeping supplied narration as the timing master.
"""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence


class CinematicSkillTimingError(ValueError):
    """Raised when narration timing is missing, ambiguous or invalid."""


def _time(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CinematicSkillTimingError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise CinematicSkillTimingError(f"{name} must be a finite non-negative number") from None
    if not math.isfinite(result) or result < 0:
        raise CinematicSkillTimingError(f"{name} must be a finite non-negative number")
    return result


@dataclass(frozen=True)
class CinematicWordCue:
    word: str
    start_seconds: float
    end_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.word, str) or not self.word.strip():
            raise CinematicSkillTimingError("word cue text must be non-empty")
        start = _time(self.start_seconds, "word.start_seconds")
        end = _time(self.end_seconds, "word.end_seconds")
        if end < start:
            raise CinematicSkillTimingError("word cue end must not precede its start")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True)
class CinematicLineCue:
    line_id: int
    start_seconds: float
    end_seconds: float
    spoken_text: str
    word_timings: tuple[CinematicWordCue, ...] = ()
    caption: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.line_id, bool) or not isinstance(self.line_id, int) or self.line_id < 0:
            raise CinematicSkillTimingError("line_id must be a non-negative integer")
        start = _time(self.start_seconds, "line.start_seconds")
        end = _time(self.end_seconds, "line.end_seconds")
        if end <= start:
            raise CinematicSkillTimingError("line end must be after line start")
        if not isinstance(self.spoken_text, str) or not self.spoken_text.strip():
            raise CinematicSkillTimingError("spoken_text must be non-empty")
        words = tuple(self.word_timings)
        if not all(isinstance(item, CinematicWordCue) for item in words):
            raise CinematicSkillTimingError("word_timings must contain CinematicWordCue values")
        if tuple(sorted(words, key=lambda item: item.start_seconds)) != words:
            raise CinematicSkillTimingError("word_timings must be ordered by start time")
        if any(item.start_seconds < start or item.end_seconds > end for item in words):
            raise CinematicSkillTimingError("word cues must remain inside their parent line")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)
        object.__setattr__(self, "word_timings", words)


class CinematicSkillNarrationDoc:
    """Minimal upstream Doc-compatible context backed by Voxora timing records.

    Word cue lookup is Unicode-aware and exact-token based. No character-share
    interpolation is performed: missing word alignment raises an explicit error.
    """

    def __init__(
        self,
        project_dir: str | Path,
        lines: Sequence[CinematicLineCue],
        *,
        prep_dir: Optional[str | Path] = None,
    ) -> None:
        if isinstance(lines, (str, bytes)) or not lines:
            raise CinematicSkillTimingError("at least one narration line is required")
        parsed = tuple(lines)
        if not parsed:
            raise CinematicSkillTimingError("at least one narration line is required")
        if not all(isinstance(item, CinematicLineCue) for item in parsed):
            raise CinematicSkillTimingError("lines must contain CinematicLineCue values")
        ids = [item.line_id for item in parsed]
        if len(ids) != len(set(ids)):
            raise CinematicSkillTimingError("line IDs must be unique")
        if tuple(sorted(parsed, key=lambda item: item.start_seconds)) != parsed:
            raise CinematicSkillTimingError("narration lines must be ordered by start time")

        self.dir = Path(project_dir).expanduser().resolve()
        self.prep = Path(prep_dir).expanduser().resolve() if prep_dir else self.dir / "assets" / "prep"
        self.fonts_dir = self.dir / "fonts"
        self.lines = {item.line_id: item for item in parsed}
        self.seg = {
            item.line_id: {
                "id": item.line_id,
                "start": item.start_seconds,
                "end": item.end_seconds,
                "vo": item.spoken_text,
                "caption": item.caption if item.caption is not None else item.spoken_text,
            }
            for item in parsed
        }
        self.duration = max(item.end_seconds for item in parsed)
        self.timing = {
            "total_duration": self.duration,
            "segments": [self.seg[item.line_id] for item in parsed],
        }
        meta_path = self.prep / "photos" / "meta.json"
        try:
            self.meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        except (OSError, json.JSONDecodeError) as exc:
            raise CinematicSkillTimingError(f"cannot read prepared photo metadata: {exc}") from exc
        self._res = None

    def L(self, line_id: int) -> float:
        """Exact start time of a narration line."""
        try:
            return self.lines[line_id].start_seconds
        except KeyError:
            raise CinematicSkillTimingError(f"unknown narration line ID: {line_id}") from None

    def E(self, line_id: int) -> float:
        """Exact end time of a narration line."""
        try:
            return self.lines[line_id].end_seconds
        except KeyError:
            raise CinematicSkillTimingError(f"unknown narration line ID: {line_id}") from None

    def W(self, line_id: int, word: str, nth: int = 0) -> float:
        """Return the measured start time of an exact spoken token occurrence."""
        if not isinstance(word, str) or not word.strip():
            raise CinematicSkillTimingError("word lookup must be non-empty")
        if isinstance(nth, bool) or not isinstance(nth, int) or nth < 0:
            raise CinematicSkillTimingError("word occurrence index must be a non-negative integer")
        try:
            line = self.lines[line_id]
        except KeyError:
            raise CinematicSkillTimingError(f"unknown narration line ID: {line_id}") from None
        def normalize_token(value: str) -> str:
            return "".join(
                char for char in value.casefold()
                if not unicodedata.category(char).startswith("P")
            )

        wanted = normalize_token(word)
        matches = [
            cue for cue in line.word_timings
            if normalize_token(cue.word) == wanted
        ]
        if nth >= len(matches):
            raise CinematicSkillTimingError(
                f"no measured timestamp for {word!r} occurrence {nth} in line {line_id}; "
                "run a word-alignment stage or choose a line-level cue"
            )
        return matches[nth].start_seconds

    def on(self, print_item, fx: float, fy: float):
        """World point at a fractional position inside an upstream Print item."""
        if not 0 <= fx <= 1 or not 0 <= fy <= 1:
            raise CinematicSkillTimingError("print coordinates must be between 0 and 1")
        try:
            from app.universal.cinematic_skill.engine import rot_point
        except (ImportError, OSError) as exc:
            raise CinematicSkillTimingError("Cinematic Skill runtime is not installed") from exc
        width, height = print_item.size_from(self.meta)
        return rot_point(
            print_item.x, print_item.y,
            (fx - 0.5) * width, (fy - 0.5) * height,
            print_item.rot,
        )

    def res(self):
        """Return upstream's world-scale resource cache for scene layout measurements."""
        if self._res is None:
            try:
                from app.universal.cinematic_skill.engine import Res
            except (ImportError, OSError) as exc:
                raise CinematicSkillTimingError(
                    "Cinematic Skill runtime is not installed"
                ) from exc
            self._res = Res(1.0, self.prep, self.fonts_dir)
        return self._res

    def map(self, name: str):
        """Load a pre-approved local map payload prepared for this project."""
        if (
            not isinstance(name, str) or not name.strip()
            or Path(name).name != name or "/" in name or "\\" in name
        ):
            raise CinematicSkillTimingError("map name must be a simple file stem")
        path = self.prep / f"map_{name}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CinematicSkillTimingError(f"cannot load prepared map {name!r}: {exc}") from exc
