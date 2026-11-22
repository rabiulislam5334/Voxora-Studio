from types import SimpleNamespace

import pytest

from app.universal.cinematic_skill_alignment import (
    CinematicSkillAlignmentError,
    StableTsNarrationAligner,
    validate_first_pass_ranges,
    validate_refined_alignment,
)


class FakeWord:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end


class FakeSegment:
    def __init__(self, words, **boundaries):
        self.words = words
        if not boundaries:
            boundaries = {"start": 0.0, "end": 1.0}
        for name, value in boundaries.items():
            setattr(self, name, value)


class FakeModel:
    def __init__(self, segments, refined_segments=None):
        self.segments = segments
        self.refined_segments = segments if refined_segments is None else refined_segments
        self.calls = []
        self.refinement_calls = []

    def align(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(segments=self.segments)

    def align_words(self, *args, **kwargs):
        self.refinement_calls.append((args, kwargs))
        return SimpleNamespace(segments=self.refined_segments)


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

    assert doc.duration == pytest.approx(4.0)  # includes trailing narration silence
    assert doc.W(1, "Voyager") == pytest.approx(0.45)
    assert doc.W(2, "interstellar") == pytest.approx(2.5)
    args, kwargs = model.calls[0]
    assert args[1] == "The Voyager crossed the heliopause.\nIt entered interstellar space."
    assert kwargs["original_split"] is True
    assert kwargs["language"] == "en"
    refine_args, refine_kwargs = model.refinement_calls[0]
    assert refine_args[0] == str(audio.resolve())
    assert refine_kwargs["inplace"] is False
    assert refine_kwargs["suppress_silence"] is True


def test_alignment_uses_constrained_refinement_timestamps(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    first_pass = [FakeSegment([FakeWord("Hello", 0.1, 0.8)])]
    refined = [FakeSegment([FakeWord("Hello", 0.2, 0.45)])]
    model = FakeModel(first_pass, refined_segments=refined)

    doc = StableTsNarrationAligner(model=model).align(
        script="Hello",
        audio_path=audio,
        language="en",
        project_dir=tmp_path,
        audio_duration_seconds=1.0,
    )

    assert doc.W(1, "Hello") == pytest.approx(0.2)
    assert model.refinement_calls


def test_alignment_rejects_zero_duration_word_after_refinement(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment([FakeWord("Hello", 0.1, 0.1)])])

    with pytest.raises(CinematicSkillAlignmentError, match="zero-duration word cue"):
        StableTsNarrationAligner(model=model).align(
            script="Hello",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=1.0,
        )


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

    with pytest.raises(CinematicSkillAlignmentError, match="returned 0 words; expected 2"):
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

def test_alignment_rejects_declared_audio_duration_shorter_than_last_word(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment(words(["Hello"], 0.1))])

    with pytest.raises(CinematicSkillAlignmentError, match="after the supplied audio"):
        StableTsNarrationAligner(model=model).align(
            script="Hello",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=0.2,
        )


def test_alignment_supports_unicode_script_tokens(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment(words(["বাংলা", "ভাষা।"], 0.1))])

    doc = StableTsNarrationAligner(model=model).align(
        script="বাংলা ভাষা।",
        audio_path=audio,
        language="bn",
        project_dir=tmp_path,
        audio_duration_seconds=1.0,
    )
    assert doc.W(1, "ভাষা") == pytest.approx(0.35)

def test_refinement_can_split_segments_and_restores_original_script_lines(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    first_pass = [
        FakeSegment(words(["The", "Voyager", "crossed", "the", "heliopause."], 0.2)),
        FakeSegment(words(["It", "entered", "interstellar", "space."], 2.0)),
    ]
    # Stable-ts align_words() is allowed to return a different segmentation.
    refined = [
        FakeSegment(words(["The", "Voyager"], 0.2)),
        FakeSegment(words(["crossed", "the", "heliopause.", "It"], 0.8)),
        FakeSegment(words(["entered", "interstellar", "space."], 2.0)),
    ]
    model = FakeModel(first_pass, refined_segments=refined)

    doc = StableTsNarrationAligner(model=model).align(
        script="The Voyager crossed the heliopause.\nIt entered interstellar space.",
        audio_path=audio,
        language="en",
        project_dir=tmp_path,
        audio_duration_seconds=4.0,
    )

    assert len(doc.lines) == 2
    assert doc.W(1, "Voyager") == pytest.approx(0.45)
    assert doc.W(2, "interstellar") == pytest.approx(2.25)



# --- validate_first_pass_ranges -------------------------------------------

LINES = ["Hello world."]


def seg(**boundaries):
    return FakeSegment(words(["Hello", "world."], 0.1), **boundaries)


def test_first_pass_rejects_segment_with_both_boundaries_absent():
    segment = seg()
    del segment.start
    del segment.end
    with pytest.raises(CinematicSkillAlignmentError, match="missing a measured boundary"):
        validate_first_pass_ranges([segment], LINES)


def test_first_pass_accepts_valid_numeric_ranges():
    validate_first_pass_ranges([seg(start=0.1, end=0.9)], LINES)
    validate_first_pass_ranges([seg(start=0, end=1)], LINES)


def test_first_pass_rejects_wrong_segment_count():
    with pytest.raises(CinematicSkillAlignmentError, match="expected 2"):
        validate_first_pass_ranges([seg()], ["One.", "Two."])


@pytest.mark.parametrize("boundaries", [{"start": 0.1}, {"end": 0.9}])
def test_first_pass_rejects_one_missing_boundary(boundaries):
    with pytest.raises(CinematicSkillAlignmentError, match="missing a measured boundary"):
        validate_first_pass_ranges([seg(**boundaries)], LINES)


@pytest.mark.parametrize("start,end", [
    ("0.1", 0.9), (0.1, "0.9"), (0.1, [0.9]),
    (True, 0.9), (0.1, True), (False, True),
    (float("nan"), 0.9), (0.1, float("nan")),
    (float("inf"), 0.9), (0.1, float("inf")), (0.1, float("-inf")),
    (-0.1, 0.9), (0.9, 0.1), (10**10000, 10**10001),
])
def test_first_pass_rejects_invalid_boundaries(start, end):
    with pytest.raises(CinematicSkillAlignmentError):
        validate_first_pass_ranges([seg(start=start, end=end)], LINES)


def test_first_pass_rejects_zero_duration_range():
    with pytest.raises(CinematicSkillAlignmentError, match="zero-duration"):
        validate_first_pass_ranges([seg(start=0.5, end=0.5)], LINES)


def test_first_pass_validation_does_not_mutate_measured_timestamps():
    segment = seg(start=0.2, end=0.8)
    validate_first_pass_ranges([segment], LINES)
    assert (segment.start, segment.end) == (0.2, 0.8)


def test_align_rejects_invalid_first_pass_before_calling_align_words(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel([FakeSegment(words(["Hello"], 0.1), start=0.4, end=0.4)])

    with pytest.raises(CinematicSkillAlignmentError, match="first-pass segment 1"):
        StableTsNarrationAligner(model=model).align(
            script="Hello",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=1.0,
        )
    assert model.refinement_calls == []


# --- validate_refined_alignment -------------------------------------------


def refined(*items):
    return SimpleNamespace(segments=[FakeSegment(list(items))])


def test_refined_accepts_slight_overlap_between_adjacent_words():
    result = refined(FakeWord("Hello", 0.1, 0.5), FakeWord("world.", 0.4, 0.8))
    flat = validate_refined_alignment(result, LINES, 1.0)
    assert [(w.start, w.end) for w in flat] == [(0.1, 0.5), (0.4, 0.8)]


def test_refined_rejects_zero_duration_word():
    result = refined(FakeWord("Hello", 0.1, 0.1), FakeWord("world.", 0.4, 0.8))
    with pytest.raises(CinematicSkillAlignmentError, match="zero-duration word cue"):
        validate_refined_alignment(result, LINES, 1.0)


def test_refined_rejects_start_regression():
    result = refined(FakeWord("Hello", 0.5, 0.7), FakeWord("world.", 0.4, 0.8))
    with pytest.raises(CinematicSkillAlignmentError, match="before the previous word start"):
        validate_refined_alignment(result, LINES, 1.0)


@pytest.mark.parametrize("start,end", [
    ("0.1", 0.5), (True, 0.5), (float("nan"), 0.5), (0.1, float("inf")),
    (-0.2, 0.5), (0.5, 0.2), (None, 0.5), (0.1, None),
])
def test_refined_rejects_invalid_word_timestamps(start, end):
    result = refined(FakeWord("Hello", start, end), FakeWord("world.", 0.6, 0.9))
    with pytest.raises(CinematicSkillAlignmentError):
        validate_refined_alignment(result, LINES, 1.0)


def test_refined_rejects_wrong_token_sequence():
    result = refined(FakeWord("world.", 0.1, 0.4), FakeWord("Hello", 0.5, 0.8))
    with pytest.raises(CinematicSkillAlignmentError, match="do not exactly match"):
        validate_refined_alignment(result, LINES, 1.0)


@pytest.mark.parametrize("items", [
    [FakeWord("Hello", 0.1, 0.4)],
    [FakeWord("Hello", 0.1, 0.4), FakeWord("world.", 0.5, 0.8), FakeWord("again", 0.9, 1.0)],
])
def test_refined_rejects_wrong_word_count(items):
    with pytest.raises(CinematicSkillAlignmentError, match="expected 2"):
        validate_refined_alignment(refined(*items), LINES, 1.0)


def test_refined_rejects_cue_beyond_audio_duration():
    result = refined(FakeWord("Hello", 0.1, 0.4), FakeWord("world.", 0.5, 1.2))
    with pytest.raises(CinematicSkillAlignmentError, match="after the supplied audio"):
        validate_refined_alignment(result, LINES, 1.0)


def test_refined_rejects_extreme_integer_duration():
    result = refined(FakeWord("Hello", 0.1, 0.4), FakeWord("world.", 0.5, 0.8))
    with pytest.raises(CinematicSkillAlignmentError, match="audio duration"):
        validate_refined_alignment(result, LINES, 10**10000)


def test_align_accepts_overlapping_words_end_to_end(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel(
        [FakeSegment(words(["Hello", "world."], 0.1))],
        refined_segments=[FakeSegment([FakeWord("Hello", 0.1, 0.5), FakeWord("world.", 0.4, 0.8)])],
    )
    doc = StableTsNarrationAligner(model=model).align(
        script="Hello world.",
        audio_path=audio,
        language="en",
        project_dir=tmp_path,
        audio_duration_seconds=1.0,
    )
    assert doc.W(1, "world") == pytest.approx(0.4)


def test_align_does_not_fall_back_to_first_pass_timestamps(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake audio")
    model = FakeModel(
        [FakeSegment(words(["Hello", "world."], 0.1), start=0.1, end=0.9)],
        refined_segments=[FakeSegment([FakeWord("Hello", 0.1, 0.1), FakeWord("world.", 0.4, 0.8)])],
    )
    with pytest.raises(CinematicSkillAlignmentError, match="zero-duration word cue"):
        StableTsNarrationAligner(model=model).align(
            script="Hello world.",
            audio_path=audio,
            language="en",
            project_dir=tmp_path,
            audio_duration_seconds=1.0,
        )
