"""Cross-page duplicate and overlap detection for content chunks."""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.analysis.embeddings import cosine_similarity
from app.models.analysis import (
    ChunkEmbedding,
    ContentChunk,
    DuplicateContentFinding,
    SimilarityFindingType,
)
from app.utils.text import normalize_whitespace

DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.92
DEFAULT_CONTENT_OVERLAP_THRESHOLD = 0.82
DEFAULT_MIN_TEXT_LENGTH = 140
MIN_UNIQUE_WORDS = 8
NEAR_DUPLICATE_MIN_LEXICAL_OVERLAP = 0.3
CONTENT_OVERLAP_MIN_LEXICAL_OVERLAP = 0.12


def detect_cross_page_duplicates(
    chunks: Sequence[ContentChunk],
    embeddings: Sequence[ChunkEmbedding],
    *,
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    overlap_threshold: float = DEFAULT_CONTENT_OVERLAP_THRESHOLD,
    min_text_length: int = DEFAULT_MIN_TEXT_LENGTH,
    max_findings: int = 50,
) -> list[DuplicateContentFinding]:
    """Detect likely duplicate or overlapping chunks across different pages."""

    embedding_by_id = {embedding.chunk_id: embedding for embedding in embeddings}
    candidate_chunks = [
        chunk
        for chunk in chunks
        if _is_meaningful_duplicate_candidate(chunk, min_text_length=min_text_length)
        and chunk.chunk_id in embedding_by_id
    ]

    findings: list[DuplicateContentFinding] = []
    for left_index, source_chunk in enumerate(candidate_chunks):
        for matched_chunk in candidate_chunks[left_index + 1 :]:
            if source_chunk.page_url == matched_chunk.page_url:
                continue

            source_embedding = embedding_by_id[source_chunk.chunk_id]
            matched_embedding = embedding_by_id[matched_chunk.chunk_id]
            score = cosine_similarity(source_embedding.vector, matched_embedding.vector)
            if score < overlap_threshold:
                continue

            lexical_overlap = lexical_overlap_score(
                source_chunk.chunk_text,
                matched_chunk.chunk_text,
            )
            finding_type = _classify_similarity(
                score,
                lexical_overlap,
                near_duplicate_threshold=near_duplicate_threshold,
                overlap_threshold=overlap_threshold,
            )
            if finding_type is None:
                continue

            findings.append(
                _build_finding(
                    finding_type=finding_type,
                    source_chunk=source_chunk,
                    matched_chunk=matched_chunk,
                    similarity_score=score,
                    lexical_overlap=lexical_overlap,
                )
            )

    findings.sort(key=lambda finding: finding.similarity_score, reverse=True)
    if max_findings <= 0:
        return []
    return findings[:max_findings]


def lexical_overlap_score(left_text: str, right_text: str) -> float:
    """Return a simple Jaccard overlap score over normalized content words."""

    left_words = _content_word_set(left_text)
    right_words = _content_word_set(right_text)
    if not left_words or not right_words:
        return 0.0
    intersection_size = len(left_words.intersection(right_words))
    union_size = len(left_words.union(right_words))
    return intersection_size / union_size


def _classify_similarity(
    similarity_score: float,
    lexical_overlap: float,
    *,
    near_duplicate_threshold: float,
    overlap_threshold: float,
) -> SimilarityFindingType | None:
    if (
        similarity_score >= near_duplicate_threshold
        and lexical_overlap >= NEAR_DUPLICATE_MIN_LEXICAL_OVERLAP
    ):
        return SimilarityFindingType.NEAR_DUPLICATE
    if (
        similarity_score >= overlap_threshold
        and lexical_overlap >= CONTENT_OVERLAP_MIN_LEXICAL_OVERLAP
    ):
        return SimilarityFindingType.CONTENT_OVERLAP
    return None


def _build_finding(
    *,
    finding_type: SimilarityFindingType,
    source_chunk: ContentChunk,
    matched_chunk: ContentChunk,
    similarity_score: float,
    lexical_overlap: float,
) -> DuplicateContentFinding:
    if finding_type == SimilarityFindingType.NEAR_DUPLICATE:
        message = (
            "Chunks on different pages appear to cover nearly the same content."
        )
    else:
        message = (
            "Chunks on different pages appear to have substantial content overlap."
        )

    return DuplicateContentFinding(
        finding_type=finding_type,
        source_chunk=source_chunk,
        matched_chunk=matched_chunk,
        similarity_score=round(similarity_score, 6),
        message=message,
        evidence_snippet=_snippet(source_chunk.chunk_text),
        metadata={
            "matched_evidence_snippet": _snippet(matched_chunk.chunk_text),
            "lexical_overlap": round(lexical_overlap, 6),
            "source_section_id": source_chunk.section_id,
            "matched_section_id": matched_chunk.section_id,
        },
    )


def _is_meaningful_duplicate_candidate(
    chunk: ContentChunk,
    *,
    min_text_length: int,
) -> bool:
    if chunk.text_length < min_text_length:
        return False
    return len(_content_word_set(chunk.chunk_text)) >= MIN_UNIQUE_WORDS


def _content_word_set(text: str) -> set[str]:
    normalized_text = normalize_whitespace(text).lower()
    words = re.findall(r"[a-z0-9]+", normalized_text)
    return {word for word in words if len(word) > 2}


def _snippet(text: str, *, max_chars: int = 220) -> str:
    normalized_text = normalize_whitespace(text)
    if len(normalized_text) <= max_chars:
        return normalized_text
    return f"{normalized_text[: max_chars - 3].rstrip()}..."
