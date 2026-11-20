from types import SimpleNamespace

import pytest

from app.universal.cinematic_skill_alignment import (
    CinematicSkillAlignmentError,
    StableTsNarrationAligner,
)


class FakeWord:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class FakeSegment:
    def __init__(self, words):
        self.words = words


class FakeModel:
    def __init__(self, segments):
        self.segments = segments
        self.calls = []

    def align(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(segments=self.segments)


def words(items, start):
    result = []
    cursor = start
    for token in items:
        result.append(FakeWord(token, cursor, cursor + 0.2))
        cursor += 0.25
    return result


def test_aligns_script_lines_and_preserves_measured_word_times(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([
        FakeSegment(words(["The", "Voyager", "crossed", "the", "heliopause."], 0.2)),
        FakeSegment(words(["It", "entered", "interstellar", "space."], 2.0)),
    ])
    aligner = StableTsNarrationAligner(model=model)

    doc = aligner.align(
        script="The Voyager crossed the heliopause.\nIt entered interstellar space.",
        audio_path=audio,
        language="en",
        project_dir=tmp_path,
        audio_duration_seconds=4.0,
    )

    assert doc.duration == pytest.approx(2.95)
    assert doc.W(1, "Voyager") == pytest.approx(0.45)
    assert doc.W(2, "interstellar") == pytest.approx(2.5)
    args, kwargs = model.calls[0]
    assert args[1] == "The Voyager crossed the heliopause.\nIt entered interstellar space."
    assert kwargs["original_split"] is True
    assert kwargs["language"] == "en"


def test_alignment_rejects_script_audio_word_mismatch(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment(words(["The", "Voyager", "arrived."], 0.1))])

    with pytest.raises(CinematicSkillAlignmentError, match="do not exactly match"):
        StableTsNarrationAligner(model=model).align(
            script="The Voyager departed.",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=2.0,
        )


def test_alignment_rejects_missing_words_and_wrong_segment_count(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")

    with pytest.raises(CinematicSkillAlignmentError, match="no word timestamps"):
        StableTsNarrationAligner(model=FakeModel([FakeSegment([])])).align(
            script="Hello world.",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=2.0,
        )

    with pytest.raises(CinematicSkillAlignmentError, match="expected 2"):
        StableTsNarrationAligner(model=FakeModel([FakeSegment(words(["Hello"], 0.1))])).align(
            script="Hello.\nWorld.",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=2.0,
        )


def test_alignment_rejects_out_of_duration_timestamps(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment([FakeWord("Hello", 1.8, 2.2)])])

    with pytest.raises(CinematicSkillAlignmentError, match="after the supplied audio"):
        StableTsNarrationAligner(model=model).align(
            script="Hello",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=2.0,
        )


def test_model_loader_is_lazy_and_receives_cpu_and_cache_settings(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment(words(["Hello"], 0.1))])
    calls = []

    def loader(name, **kwargs):
        calls.append((name, kwargs))
        return model

    aligner = StableTsNarrationAligner(
        model_loader=loader,
        model_size="tiny",
        device="cpu",
        download_root=tmp_path / "models",
    )
    aligner.align(
        script="Hello",
        audio_path=audio,
        language="en",
        project_dir=tmp_path,
        audio_duration_seconds=1.0,
    )
    assert calls == [("tiny", {"device": "cpu", "download_root": str(tmp_path / "models")})]
