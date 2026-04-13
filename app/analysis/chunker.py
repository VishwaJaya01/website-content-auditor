"""Section-aware chunking for extracted page content."""

from __future__ import annotations

from app.models.analysis import ContentChunk
from app.models.crawl import ExtractedPage, PageSection
from app.utils.text import (
    normalize_whitespace,
    rough_token_estimate,
    split_into_text_blocks,
)

DEFAULT_MAX_CHARS = 2400
DEFAULT_TARGET_CHARS = 1600
SMALL_SECTION_WARNING_CHARS = 80


def chunk_page(
    page: ExtractedPage,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    target_chars: int = DEFAULT_TARGET_CHARS,
) -> list[ContentChunk]:
    """Convert extracted page sections into deterministic analysis chunks."""

    chunks: list[ContentChunk] = []
    for section in sorted(page.sections, key=lambda item: item.order):
        section_chunks = _chunk_section(
            page,
            section,
            starting_order=len(chunks),
            max_chars=max_chars,
            target_chars=target_chars,
        )
        chunks.extend(section_chunks)
    return chunks


def _chunk_section(
    page: ExtractedPage,
    section: PageSection,
    *,
    starting_order: int,
    max_chars: int,
    target_chars: int,
) -> list[ContentChunk]:
    text = normalize_whitespace(section.text)
    if not text:
        return []

    warnings: list[str] = []
    if len(text) < SMALL_SECTION_WARNING_CHARS:
        warnings.append("short_section")

    if len(text) <= max_chars:
        return [
            _make_chunk(
                page,
                section,
                chunk_text=text,
                chunk_order=starting_order,
                section_part_index=0,
                warnings=warnings,
            )
        ]

    split_texts = _split_long_section(
        text,
        max_chars=max_chars,
        target_chars=target_chars,
    )
    chunks: list[ContentChunk] = []
    for index, chunk_text in enumerate(split_texts):
        chunk_warnings = ["split_long_section"]
        if len(chunk_text) > max_chars:
            chunk_warnings.append("oversized_chunk")
        chunks.append(
            _make_chunk(
                page,
                section,
                chunk_text=chunk_text,
                chunk_order=starting_order + index,
                section_part_index=index,
                warnings=chunk_warnings,
            )
        )
    return chunks


def _split_long_section(text: str, *, max_chars: int, target_chars: int) -> list[str]:
    blocks = split_into_text_blocks(text)
    if not blocks:
        return []

    chunks: list[str] = []
    current_blocks: list[str] = []
    current_length = 0

    for block in blocks:
        normalized_block = normalize_whitespace(block)
        if not normalized_block:
            continue

        if len(normalized_block) > max_chars:
            if current_blocks:
                chunks.append(normalize_whitespace(" ".join(current_blocks)))
                current_blocks = []
                current_length = 0
            chunks.extend(_split_oversized_block(normalized_block, target_chars))
            continue

        separator_length = 1 if current_blocks else 0
        proposed_length = current_length + separator_length + len(normalized_block)
        if current_blocks and proposed_length > target_chars:
            chunks.append(normalize_whitespace(" ".join(current_blocks)))
            current_blocks = [normalized_block]
            current_length = len(normalized_block)
        else:
            current_blocks.append(normalized_block)
            current_length = proposed_length

    if current_blocks:
        chunks.append(normalize_whitespace(" ".join(current_blocks)))

    return chunks


def _split_oversized_block(text: str, target_chars: int) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    current_words: list[str] = []
    current_length = 0

    for word in words:
        separator_length = 1 if current_words else 0
        proposed_length = current_length + separator_length + len(word)
        if current_words and proposed_length > target_chars:
            chunks.append(" ".join(current_words))
            current_words = [word]
            current_length = len(word)
        else:
            current_words.append(word)
            current_length = proposed_length

    if current_words:
        chunks.append(" ".join(current_words))
    return chunks


def _make_chunk(
    page: ExtractedPage,
    section: PageSection,
    *,
    chunk_text: str,
    chunk_order: int,
    section_part_index: int,
    warnings: list[str],
) -> ContentChunk:
    stable_section_id = _safe_id(section.section_id)
    chunk_id = f"{_safe_id(page.url)}:{stable_section_id}:{section_part_index:03d}"
    normalized_text = normalize_whitespace(chunk_text)
    return ContentChunk(
        chunk_id=chunk_id,
        page_url=page.url,
        page_title=page.title,
        page_h1=page.h1,
        section_id=section.section_id,
        section_path=section.heading_path,
        section_heading=section.heading_text,
        section_heading_level=section.heading_level,
        chunk_text=normalized_text,
        chunk_order=chunk_order,
        token_estimate=rough_token_estimate(normalized_text),
        text_length=len(normalized_text),
        warnings=warnings,
    )


def _safe_id(value: str) -> str:
    allowed_characters = []
    for character in value.lower():
        if character.isalnum():
            allowed_characters.append(character)
        elif character in {"-", "_", "."}:
            allowed_characters.append(character)
        else:
            allowed_characters.append("-")
    safe_value = "".join(allowed_characters).strip("-")
    while "--" in safe_value:
        safe_value = safe_value.replace("--", "-")
    return safe_value or "item"
