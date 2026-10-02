from __future__ import annotations

import re

# \S+ (non-whitespace runs) is Unicode-aware over Python str input, so this
# counts Bengali words exactly like English ones -- both scripts separate
# words with whitespace in ordinary prose. No language-specific handling
# needed.
_WORD_PATTERN = re.compile(r"\S+")

DEFAULT_WORDS_PER_MINUTE = 150


def count_words(text: str) -> int:
    if not text:
        return 0
    return len(_WORD_PATTERN.findall(text))


def count_characters(text: str) -> int:
    return len(text) if text else 0


def estimate_duration_seconds(
    word_count: int, words_per_minute: int = DEFAULT_WORDS_PER_MINUTE
) -> float:
    """Rough estimate only -- NOT the actual TTS-generated duration, which
    depends on the voice, speed setting, and pauses."""
    if words_per_minute <= 0 or word_count <= 0:
        return 0.0
    return (word_count / words_per_minute) * 60.0


def format_duration(seconds: float) -> str:
    """45 sec / 2 min 15 sec / 12 min -- never includes an hours component
    since scene-level scripts aren't expected to run that long."""
    total_seconds = max(0, round(seconds))
    minutes, secs = divmod(total_seconds, 60)
    if minutes == 0:
        return f"{secs} sec"
    if secs == 0:
        return f"{minutes} min"
    return f"{minutes} min {secs} sec"