from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

# Sentence enders: . ! ? … plus the Bengali/Devanagari danda (। ॥).
_SENTENCE_END_RE = re.compile(r"[.!?\u2026\u0964\u0965]+[\"'\u201d\u2019)\]]*(?=\s|$)")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[,;:\u2014\u2013])\s+")
_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "st", "e.g", "i.e"}
_JOINERS = {"\u200c", "\u200d"}
_VIRAMA_BN = "\u09cd"


def is_speakable(text: str) -> bool:
    """True if the text contains at least one letter or digit. Punctuation-
    only pieces ('...', '--') make TTS providers return no audio."""
    return any(ch.isalnum() for ch in text)


def split_sentences(text: str) -> List[str]:
    """Split on sentence-ending punctuation followed by whitespace, so
    decimals ('3.5') and URLs stay intact. Common abbreviations ('Dr.') do not
    end a sentence. Never drops text."""
    text = text.strip()
    sentences: List[str] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(text):
        end = match.end()
        words = text[start:match.start()].split()
        last_word = words[-1].lower() if words else ""
        if match.group(0)[0] == "." and last_word in _ABBREVIATIONS:
            continue
        piece = text[start:end].strip()
        if piece:
            sentences.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _safe_cut(text: str, index: int) -> int:
    """Move a cut point left so it never splits a Bengali conjunct or a
    combining mark from its base letter."""
    while index > 1 and (
        unicodedata.category(text[index]) in ("Mn", "Mc", "Me")
        or text[index] in _JOINERS
        or text[index - 1] == _VIRAMA_BN
    ):
        index -= 1
    return index


def _hard_split(text: str, max_chars: int) -> List[str]:
    """Last resort: split at the last space before the limit (never inside a
    word). Only a single 'word' longer than max_chars is cut mid-token."""
    pieces: List[str] = []
    remaining = text.strip()
    while len(remaining) > max_chars:
        cut = remaining.rfind(" ", 0, max_chars + 1)
        if cut <= 0:
            cut = _safe_cut(remaining, max_chars)
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def _pack(parts: List[str], max_chars: int) -> List[str]:
    packed: List[str] = []
    current = ""
    for part in parts:
        if not current:
            current = part
        elif len(current) + 1 + len(part) <= max_chars:
            current = f"{current} {part}"
        else:
            packed.append(current)
            current = part
    if current:
        packed.append(current)
    return packed


def _fit_sentence(sentence: str, max_chars: int) -> List[str]:
    """Split one over-long sentence at clause boundaries, then hard limit."""
    if len(sentence) <= max_chars:
        return [sentence]
    clauses = [c for c in _CLAUSE_SPLIT_RE.split(sentence) if c.strip()]
    pieces: List[str] = []
    for clause in clauses:
        pieces.extend(_hard_split(clause, max_chars) if len(clause) > max_chars else [clause])
    return _pack(pieces, max_chars)


def chunk_text(text: str, max_chars: int, per_sentence: bool) -> List[Tuple[str, bool]]:
    """Split text into synthesis chunks, returned as (chunk_text, ends_sentence).

    Priority: sentence -> clause -> safe character limit; words are never cut.
    per_sentence=True keeps one sentence per chunk (so a sentence pause can be
    inserted between them); otherwise whole sentences are packed together up
    to max_chars to minimise provider requests. Non-speakable pieces are
    dropped."""
    sentences = split_sentences(text)
    result: List[Tuple[str, bool]] = []

    if per_sentence:
        for sentence in sentences:
            fitted = [p for p in _fit_sentence(sentence, max_chars) if is_speakable(p)]
            for i, piece in enumerate(fitted):
                result.append((piece, i == len(fitted) - 1))
        return result

    fitted_all: List[str] = []
    for sentence in sentences:
        fitted_all.extend(_fit_sentence(sentence, max_chars))
    for piece in _pack(fitted_all, max_chars):
        if is_speakable(piece):
            result.append((piece, True))
    return result