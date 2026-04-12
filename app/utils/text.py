"""Text cleanup helpers shared by extraction and future analysis steps."""

from __future__ import annotations

import re

WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and trim surrounding space."""

    return WHITESPACE_RE.sub(" ", text).strip()


def has_letters(text: str) -> bool:
    """Return whether text contains at least one alphabetic character."""

    return any(character.isalpha() for character in text)

