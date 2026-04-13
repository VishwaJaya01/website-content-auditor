"""Text cleanup helpers shared by extraction and future analysis steps."""

from __future__ import annotations

import re

WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and trim surrounding space."""

    return WHITESPACE_RE.sub(" ", text).strip()


def has_letters(text: str) -> bool:
    """Return whether text contains at least one alphabetic character."""

    return any(character.isalpha() for character in text)


def rough_token_estimate(text: str) -> int:
    """Estimate token count with a simple local-model-friendly heuristic."""

    normalized_text = normalize_whitespace(text)
    if not normalized_text:
        return 0
    return max(1, round(len(normalized_text) / 4))


def split_into_text_blocks(text: str) -> list[str]:
    """Split text into paragraph-like blocks with a sentence fallback."""

    stripped_text = text.strip()
    if not stripped_text:
        return []

    paragraph_blocks = [
        normalize_whitespace(block)
        for block in re.split(r"\n\s*\n+", stripped_text)
        if normalize_whitespace(block)
    ]
    if len(paragraph_blocks) > 1:
        return paragraph_blocks

    line_blocks = [
        normalize_whitespace(block)
        for block in stripped_text.splitlines()
        if normalize_whitespace(block)
    ]
    if len(line_blocks) > 1:
        return line_blocks

    return [
        normalize_whitespace(sentence)
        for sentence in SENTENCE_BOUNDARY_RE.split(stripped_text)
        if normalize_whitespace(sentence)
    ]
