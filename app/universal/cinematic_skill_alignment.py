"""Optional local word alignment for supplied Voxora scripts and narration.

The adapter uses Stable-ts (MIT) with OpenAI Whisper model weights locally.
It never uploads audio, and it fails closed when aligned words do not match
the supplied script. The optional dependency is deliberately not installed
with Voxora's core requirements.
"""
from __future__ import annotations

import math
import numbers
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from app.universal.cinematic_skill_timing import (
    CinematicLineCue,
    CinematicSkillNarrationDoc,
    CinematicSkillTimingError,
    CinematicWordCue,
)


class CinematicSkillAlignmentError(RuntimeError):
    """Raised when local word alignment cannot safely map audio to the script."""


def _normalise_token(value: str) -> str:
    return "".join(
        char.casefold()
        for char in value
        if not unicodedata.category(char).startswith("P")
        and not char.isspace()
    )


def _script_lines(script: str) -> list[str]:
    if not isinstance(script, str) or not script.strip():
        raise CinematicSkillAlignmentError("script must be a non-empty string")
    lines = [line.strip() for line in script.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return [line for line in lines if line]


def _is_real_number(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, numbers.Real)


def _is_finite_number(value) -> bool:
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _safe_repr(value) -> str:
    try:
        return repr(value)
    except (OverflowError, ValueError):
        return f"<{type(value).__name__}>"


def _check_range(start, end, label: str, noun: str = "range") -> None:
    if not _is_real_number(start) or not _is_real_number(end):
        raise CinematicSkillAlignmentError(
            f"{label} has a non-numeric or boolean boundary "
            f"(start={_safe_repr(start)}, end={_safe_repr(end)})"
        )
    if not _is_finite_number(start) or not _is_finite_number(end):
        raise CinematicSkillAlignmentError(
            f"{label} has a non-finite boundary (start={start!r}, end={end!r})"
        )
    if start < 0 or end < 0:
        raise CinematicSkillAlignmentError(
            f"{label} has a negative boundary (start={start!r}, end={end!r})"
        )
    if end < start:
        raise CinematicSkillAlignmentError(
            f"{label} ends before it starts (start={start!r}, end={end!r})"
        )
    if end == start:
        raise CinematicSkillAlignmentError(
            f"{label} is a zero-duration {noun} (start={start!r}, end={end!r})"
        )


def validate_first_pass_ranges(segments, lines) -> None:
    try:
        segment_list = list(segments)
    except TypeError:
        raise CinematicSkillAlignmentError(
            "Stable-ts first pass returned no segment collection"
        ) from None
    if len(segment_list) != len(lines):
        raise CinematicSkillAlignmentError(
            f"first-pass alignment returned {len(segment_list)} segments; "
            f"expected {len(lines)} from the supplied script"
        )
    for index, segment in enumerate(segment_list, start=1):
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        label = f"first-pass segment {index}"
        if start is None or end is None:
            raise CinematicSkillAlignmentError(
                f"{label} is missing a measured boundary "
                f"(start={start!r}, end={end!r})"
            )
        _check_range(start, end, label)


def validate_refined_alignment(result, lines, duration) -> list:
    if (
        not _is_real_number(duration)
        or not _is_finite_number(duration)
        or duration <= 0
    ):
        raise CinematicSkillAlignmentError("audio duration must be a finite positive number")
    segments = getattr(result, "segments", None)
    if segments is None:
        raise CinematicSkillAlignmentError(
            "Stable-ts refinement returned no segment collection"
        )
    refined_words = [
        word for segment in segments
        for word in (getattr(segment, "words", None) or [])
    ]
    expected_tokens = [token for line in lines for token in line.split()]
    line_ids = [
        line_id for line_id, line in enumerate(lines, start=1)
        for _ in line.split()
    ]
    if len(refined_words) != len(expected_tokens):
        raise CinematicSkillAlignmentError(
            f"refined alignment returned {len(refined_words)} words; "
            f"expected {len(expected_tokens)} from the supplied script"
        )
    for i, (word, token) in enumerate(zip(refined_words, expected_tokens)):
        actual_text = getattr(word, "word", None)
        actual = _normalise_token(actual_text) if isinstance(actual_text, str) else ""
        if actual != _normalise_token(token):
            raise CinematicSkillAlignmentError(
                f"aligned words do not exactly match the supplied script at word "
                f"{i + 1} (script line {line_ids[i]}); "
                "no cues were accepted. Check transcription/script wording."
            )
    previous_start = None
    for i, word in enumerate(refined_words):
        start = getattr(word, "start", None)
        end = getattr(word, "end", None)
        label = f"refined word {i + 1} {getattr(word, 'word', None)!r} (script line {line_ids[i]})"
        _check_range(start, end, label, noun="word cue")
        if previous_start is not None and start < previous_start:
            raise CinematicSkillAlignmentError(
                f"{label} starts at {start!r}, before the previous word start {previous_start!r}"
            )
        previous_start = start
        if end > duration:
            raise CinematicSkillAlignmentError(
                f"{label} ends at {end!r}, after the supplied audio duration {duration!r}"
            )
    return refined_words


class StableTsNarrationAligner:
    """Align supplied narration audio to the exact supplied script, locally.

    Stable-ts is an optional MIT-licensed dependency. Its upstream repository
    is archived, so keep it isolated behind this adapter and pin the runtime.
    The default tiny model is intended as a low-memory starting point, not a
    guarantee of acceptable accuracy for every accent, language or recording.
    """

    def __init__(
        self,
        *,
        model=None,
        model_loader: Optional[Callable] = None,
        model_size: str = "tiny",
        device: str = "cpu",
        download_root: Optional[str | Path] = None,
    ) -> None:
        if model is None and model_loader is not None and not callable(model_loader):
            raise TypeError("model_loader must be callable")
        if not isinstance(model_size, str) or not model_size.strip():
            raise ValueError("model_size must be a non-empty string")
        if device not in {"cpu", "cuda"}:
            raise ValueError("device must be 'cpu' or 'cuda'")
        self._model = model
        self._model_loader = model_loader
        self.model_size = model_size
        self.device = device
        self.download_root = Path(download_root).expanduser() if download_root else None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            if self._model_loader is not None:
                loader = self._model_loader
            else:
                import stable_whisper
                loader = stable_whisper.load_model
        except (ImportError, OSError) as exc:
            raise CinematicSkillAlignmentError(
                "Stable-ts local runtime is unavailable. Install the optional "
                "requirements-word-alignment.txt; no paid service is used."
            ) from exc
        kwargs = {"device": self.device}
        if self.download_root is not None:
            self.download_root.mkdir(parents=True, exist_ok=True)
            kwargs["download_root"] = str(self.download_root)
        try:
            self._model = loader(self.model_size, **kwargs)
        except Exception as exc:
            raise CinematicSkillAlignmentError(
                f"could not load local Whisper model {self.model_size!r}: {exc}"
            ) from exc
        return self._model

    def align(
        self,
        *,
        script: str,
        audio_path: str | Path,
        language: str,
        project_dir: str | Path,
        audio_duration_seconds: float,
    ) -> CinematicSkillNarrationDoc:
        """Return exact word cues grouped by non-empty script line.

        original_split=True asks Stable-ts to preserve the script's line
        boundaries during the first pass. The constrained refinement may split
        or merge segments, so its flattened word sequence is validated against
        the complete script and then regrouped by the original line word counts.
        Omissions, insertions and reordered words are rejected.
        """
        lines = _script_lines(script)
        if not isinstance(language, str) or not language.strip():
            raise CinematicSkillAlignmentError("language is required (e.g. 'en' or 'bn')")
        if (
            not _is_real_number(audio_duration_seconds)
            or not _is_finite_number(audio_duration_seconds)
            or audio_duration_seconds <= 0
        ):
            raise CinematicSkillAlignmentError("audio duration must be a finite positive number")
        duration = float(audio_duration_seconds)
        audio = Path(audio_path).expanduser().resolve()
        if not audio.is_file():
            raise CinematicSkillAlignmentError(f"narration audio file does not exist: {audio}")

        model = self._load_model()
        try:
            result = model.align(
                str(audio),
                "\n".join(lines),
                language=language,
                original_split=True,
                stream=True,
                verbose=False,
                suppress_silence=True,
            )
        except Exception as exc:
            raise CinematicSkillAlignmentError(
                f"local word alignment failed for language {language!r}: {exc}"
            ) from exc

        validate_first_pass_ranges(getattr(result, "segments", None), lines)

        # Stable-ts' align() establishes script-line ranges, but its first-pass
        # fallback can leave instant words or stretch a boundary word across
        # trailing silence. Re-align each word inside those measured line
        # ranges using Stable-ts' constrained align_words() pass.
        refine_words = getattr(model, "align_words", None)
        if not callable(refine_words):
            raise CinematicSkillAlignmentError(
                "the installed Stable-ts runtime does not expose align_words(); "
                "install the pinned optional runtime from requirements-word-alignment.txt"
            )
        try:
            result = refine_words(
                str(audio),
                result,
                language=language,
                inplace=False,
                stream=True,
                verbose=False,
                suppress_silence=True,
            )
        except Exception as exc:
            raise CinematicSkillAlignmentError(
                f"constrained word-timing refinement failed for language {language!r}: {exc}"
            ) from exc

        if result is None:
            raise CinematicSkillAlignmentError(
                "Stable-ts could not refine the first-pass word alignment"
            )

        refined_words = validate_refined_alignment(result, lines, duration)

        cues = []
        word_offset = 0
        for line_id, source_line in enumerate(lines, start=1):
            line_tokens = source_line.split()
            words = refined_words[word_offset:word_offset + len(line_tokens)]
            word_offset += len(line_tokens)
            word_cues = []
            for word in words:
                token = getattr(word, "word", None)
                try:
                    word_cues.append(CinematicWordCue(
                        token, getattr(word, "start", None), getattr(word, "end", None)
                    ))
                except (TypeError, CinematicSkillTimingError) as exc:
                    raise CinematicSkillAlignmentError(
                        f"invalid word timing in script line {line_id}: {exc}"
                    ) from exc

            try:
                cues.append(CinematicLineCue(
                    line_id=line_id,
                    start_seconds=min(item.start_seconds for item in word_cues),
                    end_seconds=max(item.end_seconds for item in word_cues),
                    spoken_text=source_line,
                    word_timings=tuple(word_cues),
                    caption=source_line,
                ))
            except CinematicSkillTimingError as exc:
                raise CinematicSkillAlignmentError(
                    f"invalid line timing for script line {line_id}: {exc}"
                ) from exc

        try:
            return CinematicSkillNarrationDoc(project_dir, cues, duration_seconds=duration)
        except CinematicSkillTimingError as exc:
            raise CinematicSkillAlignmentError(
                f"could not create narration timing document: {exc}"
            ) from exc
