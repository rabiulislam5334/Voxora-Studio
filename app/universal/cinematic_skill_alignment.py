"""Optional local word alignment for supplied Voxora scripts and narration.

The adapter uses Stable-ts (MIT) with OpenAI Whisper model weights locally.
It never uploads audio, and it fails closed when aligned words do not match
the supplied script. The optional dependency is deliberately not installed
with Voxora's core requirements.
"""
from __future__ import annotations

import math
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
        if isinstance(audio_duration_seconds, bool) or not isinstance(audio_duration_seconds, (int, float)):
            raise CinematicSkillAlignmentError("audio duration must be a finite positive number")
        duration = float(audio_duration_seconds)
        if not math.isfinite(duration) or duration <= 0:
            raise CinematicSkillAlignmentError("audio duration must be a finite positive number")
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

        segments = getattr(result, "segments", None)
        if segments is None:
            raise CinematicSkillAlignmentError(
                "Stable-ts refinement returned no segment collection"
            )

        # align_words() may split or merge the first-pass script segments.
        # Validate the complete ordered word stream, then restore the original
        # script-line grouping by each line's known word count. Timestamps are
        # retained verbatim; only their container grouping is reconstructed.
        refined_words = [
            word
            for segment in segments
            for word in (getattr(segment, "words", None) or [])
        ]
        expected_tokens = [
            token for source_line in lines for token in source_line.split()
        ]
        if len(refined_words) != len(expected_tokens):
            raise CinematicSkillAlignmentError(
                f"refined alignment returned {len(refined_words)} words; "
                f"expected {len(expected_tokens)} from the supplied script"
            )

        cues = []
        word_offset = 0
        for line_id, source_line in enumerate(lines, start=1):
            line_tokens = source_line.split()
            words = refined_words[word_offset:word_offset + len(line_tokens)]
            word_offset += len(line_tokens)
            actual = [
                _normalise_token(getattr(word, "word", ""))
                if isinstance(getattr(word, "word", None), str) else ""
                for word in words
            ]
            expected = [_normalise_token(token) for token in line_tokens]
            if actual != expected:
                raise CinematicSkillAlignmentError(
                    f"aligned words do not exactly match script line {line_id}; "
                    "no cues were accepted. Check transcription/script wording."
                )

            word_cues = []
            for word in words:
                token = getattr(word, "word", None)
                start = getattr(word, "start", None)
                end = getattr(word, "end", None)
                try:
                    cue = CinematicWordCue(token, start, end)
                except (TypeError, CinematicSkillTimingError) as exc:
                    raise CinematicSkillAlignmentError(
                        f"invalid word timing in script line {line_id}: {exc}"
                    ) from exc
                if cue.end_seconds <= cue.start_seconds:
                    raise CinematicSkillAlignmentError(
                        f"Stable-ts produced a zero-duration word cue for {token!r} "
                        f"in script line {line_id}, even after constrained refinement"
                    )
                word_cues.append(cue)

            start_seconds = min(item.start_seconds for item in word_cues)
            end_seconds = max(item.end_seconds for item in word_cues)
            if end_seconds > duration:
                raise CinematicSkillAlignmentError(
                    f"aligned script line {line_id} ends after the supplied audio duration"
                )
            try:
                cues.append(CinematicLineCue(
                    line_id=line_id,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
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
