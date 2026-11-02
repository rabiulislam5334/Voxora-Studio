"""Phase 1 / Step 1 -- characterization tests for the text engines.

These tests pin down what the code does TODAY (chunker, narration parser,
narration plan) so later phases can change things deliberately instead of
by accident. They contain no UI, no network and no FFmpeg.

Conventions
-----------
* Plain tests describe current behaviour that should be preserved.
* Tests named ``test_current_...`` document behaviour that is accepted for
  now but that a later step may change on purpose. If one of those fails
  after a change, update it in the same commit and say why.
"""
from __future__ import annotations

import time
import unicodedata

import pytest

from app.core.constants import NARRATION_MAX_CHUNK_CHARS
from app.text.chunker import (
    _hard_split,
    chunk_text,
    is_speakable,
    split_sentences,
)
from app.text.narration_parser import PauseItem, TextItem, parse_script
from app.text.narration_plan import Chunk, Silence, collapse_silences, plan_scene

VIRAMA_BN = "\u09cd"


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------


def _parsed_items(text: str):
    parsed = parse_script(text)
    return [
        [
            ("text", i.text, i.style) if isinstance(i, TextItem) else ("pause", i.ms)
            for i in paragraph.items
        ]
        for paragraph in parsed.paragraphs
    ]


def _plan_items(text: str, sentence_ms: int = 300, paragraph_ms: int = 700, scene_index: int = 1):
    plan = plan_scene(
        text, scene_index, sentence_pause_ms=sentence_ms, paragraph_pause_ms=paragraph_ms
    )
    out = []
    for item in plan.items:
        if isinstance(item, Chunk):
            out.append(("chunk", item.id, item.text, item.style))
        else:
            out.append(("silence", item.ms, item.explicit))
    return out, plan


# ----------------------------------------------------------------------
# is_speakable / split_sentences
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("...", False),
        ("--", False),
        ("", False),
        ("a", True),
        ("\u09eb", True),   # Bengali digit 5
        ("\u0964", False),  # danda alone
    ],
)
def test_is_speakable(text, expected):
    assert is_speakable(text) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hello world. How are you? Fine!", ["Hello world.", "How are you?", "Fine!"]),
        # abbreviation and decimal/URL stay inside one sentence
        ("Dr. Smith paid 3.5 dollars at example.com. Done.",
         ["Dr. Smith paid 3.5 dollars at example.com.", "Done."]),
        # Bengali danda and double danda end sentences
        ("আমি ভালো আছি। তুমি কেমন আছো? ধন্যবাদ॥ শেষ",
         ["আমি ভালো আছি।", "তুমি কেমন আছো?", "ধন্যবাদ॥", "শেষ"]),
        # a closing quote stays with its sentence
        ('He said "stop." Then left.', ['He said "stop."', "Then left."]),
        ("   ", []),
        ("No end punctuation", ["No end punctuation"]),
        ("Wait... what? Yes!!", ["Wait...", "what?", "Yes!!"]),
    ],
)
def test_split_sentences(text, expected):
    assert split_sentences(text) == expected


# ----------------------------------------------------------------------
# chunk_text -- exact cases
# ----------------------------------------------------------------------


def test_per_sentence_mode_keeps_one_sentence_per_chunk():
    assert chunk_text("One. Two. Three.", 100, True) == [
        ("One.", True), ("Two.", True), ("Three.", True),
    ]


def test_packed_mode_joins_sentences_up_to_the_limit():
    assert chunk_text("One. Two. Three.", 100, False) == [("One. Two. Three.", True)]
    assert chunk_text("One. Two. Three.", 10, False) == [("One. Two.", True), ("Three.", True)]


def test_long_sentence_splits_at_clauses_and_only_last_piece_ends_sentence():
    text = "alpha beta gamma, delta epsilon zeta, eta theta iota kappa."
    assert chunk_text(text, 25, True) == [
        ("alpha beta gamma,", False),
        ("delta epsilon zeta,", False),
        ("eta theta iota kappa.", True),
    ]


def test_words_are_never_cut_when_a_space_is_available():
    result = chunk_text("word " * 10, 12, True)
    assert [piece for piece, _ in result] == ["word word"] * 5
    assert [flag for _, flag in result] == [False, False, False, False, True]


def test_single_token_longer_than_limit_is_cut_mid_token():
    # Documented last resort: only a single unbroken token is ever cut.
    assert chunk_text("x" * 30, 10, True) == [
        ("x" * 10, False), ("x" * 10, False), ("x" * 10, True),
    ]
    assert _hard_split("abcdefghij", 4) == ["abcd", "efgh", "ij"]
    assert _hard_split("aaa bbb ccc", 5) == ["aaa", "bbb", "ccc"]


@pytest.mark.parametrize("text", ["... -- !!", "", "   "])
@pytest.mark.parametrize("per_sentence", [True, False])
def test_unspeakable_or_empty_text_yields_no_chunks(text, per_sentence):
    assert chunk_text(text, 50, per_sentence) == []


def test_bengali_words_split_on_spaces():
    text = "আমরা মহাসাগরের গভীরতা নিয়ে কথা বলব"
    assert chunk_text(text, 12, True) == [
        ("আমরা", False),
        ("মহাসাগরের", False),
        ("গভীরতা নিয়ে", False),
        ("কথা বলব", True),
    ]


# ----------------------------------------------------------------------
# chunk_text -- invariants (property-style, no extra dependency)
# ----------------------------------------------------------------------

_SAMPLES = [
    "The quick brown fox jumps over the lazy dog. " * 12,
    "A very long sentence without any terminal punctuation " * 15,
    "আজকের ভিডিওতে আমরা মহাসাগরের গভীরতা নিয়ে কথা বলব। এটি একটি দীর্ঘ যাত্রা। " * 6,
    "Mixed ভাষা text, মারিয়ানা খাত, is 10,994 m deep; Dr. Smith measured it. " * 8,
    ("ক্ষত্রিয়" * 12),  # one unbroken Bengali conjunct-heavy token
]


@pytest.mark.parametrize("sample", _SAMPLES)
@pytest.mark.parametrize("max_chars", [8, 13, 40, 120, 1000])
@pytest.mark.parametrize("per_sentence", [True, False])
def test_chunk_invariants(sample, max_chars, per_sentence):
    chunks = [piece for piece, _ in chunk_text(sample, max_chars, per_sentence)]
    assert chunks, "speakable input must produce chunks"

    # 1. nothing is lost: the characters (ignoring whitespace) are preserved in order
    assert "".join("".join(chunks).split()) == "".join(sample.split())

    # 2. no chunk is empty or exceeds the limit (an unbroken token may only be
    #    cut AT the limit, never beyond it)
    for piece in chunks:
        assert piece.strip() == piece and piece
        assert len(piece) <= max_chars

    # 3. a chunk never starts with a combining mark / joiner or ends in a virama,
    #    i.e. Bengali conjuncts and vowel signs are not torn from their base letter
    for piece in chunks:
        assert unicodedata.category(piece[0]) not in ("Mn", "Mc", "Me")
        assert piece[0] not in "\u200c\u200d"
        assert piece[-1] != VIRAMA_BN


@pytest.mark.parametrize("max_chars", [20, 60, 1000])
def test_no_word_is_split_when_words_fit_the_limit(max_chars):
    text = "The quick brown fox jumps over the lazy dog. " * 30
    chunks = [piece for piece, _ in chunk_text(text, max_chars, False)]
    assert " ".join(chunks).split() == text.split()


def test_default_provider_limit_is_respected_for_very_long_sentence():
    text = ("lorem ipsum dolor sit amet " * 400).strip() + "."  # ~10,800 chars, one sentence
    chunks = [piece for piece, _ in chunk_text(text, NARRATION_MAX_CHUNK_CHARS, True)]
    assert len(chunks) >= 10
    assert all(len(piece) <= NARRATION_MAX_CHUNK_CHARS for piece in chunks)
    assert " ".join(chunks).split() == text.split()


def test_twenty_thousand_words_chunk_quickly():
    text = ("This is a plain English sentence about space and time. " * 2000)  # ~22k words
    started = time.perf_counter()
    chunks = chunk_text(text, NARRATION_MAX_CHUNK_CHARS, False)
    elapsed = time.perf_counter() - started
    assert len(chunks) > 100
    assert elapsed < 10, f"chunking took {elapsed:.2f}s (generous limit, guards against O(n^2) regressions)"


# ----------------------------------------------------------------------
# parse_script
# ----------------------------------------------------------------------


def test_blank_lines_separate_paragraphs_single_newlines_become_spaces():
    assert _parsed_items("Hello.\n\nWorld.") == [[("text", "Hello.", None)], [("text", "World.", None)]]
    assert _parsed_items("Line one\nline two") == [[("text", "Line one line two", None)]]
    assert _parsed_items("A\r\nB\r\n\r\nC") == [[("text", "A B", None)], [("text", "C", None)]]


def test_empty_and_whitespace_only_scripts_parse_to_nothing():
    assert _parsed_items("") == []
    assert _parsed_items("   \n\n  ") == []
    assert parse_script(None).paragraphs == []  # type: ignore[arg-type]


def test_pause_marker_forms():
    assert _parsed_items("A [pause] B [pause 500ms] C [pause 1.5s] D [pause 2 s]") == [[
        ("text", "A", None), ("pause", 700),
        ("text", "B", None), ("pause", 500),
        ("text", "C", None), ("pause", 1500),
        ("text", "D", None), ("pause", 2000),
    ]]
    assert _parsed_items("[pause 1s]") == [[("pause", 1000)]]
    assert _parsed_items("Hi [ pause 2s ] there") == [[
        ("text", "Hi", None), ("pause", 2000), ("text", "there", None),
    ]]


def test_invalid_pause_is_dropped_with_a_warning_and_never_spoken():
    parsed = parse_script("A [pause abc] B")
    assert _parsed_items("A [pause abc] B") == [[("text", "A", None), ("text", "B", None)]]
    assert len(parsed.warnings) == 1 and "invalid pause" in parsed.warnings[0].lower()


def test_overlong_pause_is_clamped_to_sixty_seconds_with_a_warning():
    parsed = parse_script("A [pause 120s] B")
    pauses = [i.ms for p in parsed.paragraphs for i in p.items if isinstance(i, PauseItem)]
    assert pauses == [60000]
    assert len(parsed.warnings) == 1 and "60 seconds" in parsed.warnings[0]


def test_current_zero_length_pause_is_silently_dropped():
    assert _parsed_items("A [pause 0ms] B") == [[("text", "A", None), ("text", "B", None)]]
    assert parse_script("A [pause 0ms] B").warnings == []


def test_style_tags_are_removed_from_speech_and_are_sticky_metadata():
    parsed = parse_script("[whisper] soft [calm] gentle [WHISPER] again")
    assert _parsed_items("[whisper] soft [calm] gentle [WHISPER] again") == [[
        ("text", "soft", "whisper"), ("text", "gentle", "calm"), ("text", "again", "whisper"),
    ]]
    assert parsed.style_tags == ["whisper", "calm"]  # unique, in first-seen order


def test_current_unknown_bracket_tags_are_spoken_aloud():
    # Only [pause...] and the nine recognised style tags are stripped. Anything
    # else in square brackets stays in the spoken text. Step 7 (Script
    # Intelligence) will WARN about this; today it is simply read out.
    assert _parsed_items("Read [music] aloud [sfx: boom]") == [
        [("text", "Read [music] aloud [sfx: boom]", None)]
    ]
    # "[pauses]" is not a pause marker (word boundary), so it is spoken too.
    assert _parsed_items("there [pauses] x") == [[("text", "there [pauses] x", None)]]


def test_parser_never_mutates_or_depends_on_input_object():
    original = "Keep [pause 1s] this."
    parse_script(original)
    assert original == "Keep [pause 1s] this."


# ----------------------------------------------------------------------
# plan_scene / collapse_silences
# ----------------------------------------------------------------------


def test_plan_inserts_sentence_pause_between_sentences_only():
    items, _ = _plan_items("One. Two.")
    assert items == [
        ("chunk", "scene_01_chunk_001", "One.", None),
        ("silence", 300, False),
        ("chunk", "scene_01_chunk_002", "Two.", None),
    ]


def test_plan_uses_paragraph_pause_between_paragraphs():
    items, _ = _plan_items("One.\n\nTwo.")
    assert items == [
        ("chunk", "scene_01_chunk_001", "One.", None),
        ("silence", 700, False),
        ("chunk", "scene_01_chunk_002", "Two.", None),
    ]


def test_explicit_pause_replaces_adjacent_automatic_pauses():
    items, _ = _plan_items("A. [pause 1s] B.")
    assert items == [
        ("chunk", "scene_01_chunk_001", "A.", None),
        ("silence", 1000, True),
        ("chunk", "scene_01_chunk_002", "B.", None),
    ]


def test_neighbouring_explicit_pauses_add_up():
    items, _ = _plan_items("A.[pause]\n\n[pause 2s]B.")
    assert items == [
        ("chunk", "scene_01_chunk_001", "A.", None),
        ("silence", 2700, True),
        ("chunk", "scene_01_chunk_002", "B.", None),
    ]


def test_zero_sentence_pause_packs_sentences_into_one_chunk():
    items, _ = _plan_items("One. Two.", sentence_ms=0)
    assert items == [("chunk", "scene_01_chunk_001", "One. Two.", None)]


def test_chunk_ids_embed_scene_index_and_count_across_paragraphs():
    plan = plan_scene("A.\n\nB.\n\nC.", 12, sentence_pause_ms=0, paragraph_pause_ms=0)
    assert [c.id for c in plan.chunks] == [
        "scene_12_chunk_001", "scene_12_chunk_002", "scene_12_chunk_003",
    ]


def test_trailing_automatic_silence_is_dropped_but_trailing_explicit_is_kept():
    items, _ = _plan_items("Done.\n\n")
    assert items == [("chunk", "scene_01_chunk_001", "Done.", None)]
    items, _ = _plan_items("Done. [pause 1s]")
    assert items[-1] == ("silence", 1000, True)


def test_pause_only_scene_plans_a_single_explicit_silence_and_no_chunks():
    items, plan = _plan_items("[pause 1s]")
    assert items == [("silence", 1000, True)]
    assert plan.chunks == []


def test_empty_scene_plans_nothing():
    items, plan = _plan_items("")
    assert items == [] and plan.chunks == []


def test_style_tag_reaches_chunk_metadata_but_not_chunk_text():
    items, plan = _plan_items("[whisper] Hi. [calm] Yo.")
    assert items == [
        ("chunk", "scene_01_chunk_001", "Hi.", "whisper"),
        ("silence", 300, False),
        ("chunk", "scene_01_chunk_002", "Yo.", "calm"),
    ]
    assert plan.style_tags == ["whisper", "calm"]
    assert all("[" not in c.text for c in plan.chunks)


def test_plan_carries_parser_warnings():
    _, plan = _plan_items("A [pause abc] B")
    assert len(plan.warnings) == 1


def test_plan_is_deterministic():
    text = "Intro. [pause 1s] আমরা কথা বলব। Done!\n\nEnd."
    assert _plan_items(text) == _plan_items(text)


def test_bengali_scene_is_planned_per_sentence():
    items, _ = _plan_items("আমি ভালো আছি। তুমি কেমন আছো?")
    assert items == [
        ("chunk", "scene_01_chunk_001", "আমি ভালো আছি।", None),
        ("silence", 300, False),
        ("chunk", "scene_01_chunk_002", "তুমি কেমন আছো?", None),
    ]


def test_collapse_silences_rules():
    assert collapse_silences([Silence(300, False), Silence(700, False)]) == []  # trailing auto dropped
    merged = collapse_silences([
        Chunk("a", "x"), Silence(300, False), Silence(500, True), Silence(200, True),
        Chunk("b", "y"), Silence(100, False),
    ])
    assert merged == [Chunk("a", "x"), Silence(700, True), Chunk("b", "y")]
    # without explicit pauses the LONGER automatic pause wins (they do not add)
    assert collapse_silences([
        Chunk("a", "x"), Silence(300, False), Silence(700, False), Chunk("b", "y"),
    ]) == [Chunk("a", "x"), Silence(700, False), Chunk("b", "y")]
