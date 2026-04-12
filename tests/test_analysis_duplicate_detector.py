"""Tests for cross-page duplicate and overlap detection."""

from app.analysis.duplicate_detector import detect_cross_page_duplicates
from app.analysis.embeddings import build_chunk_embedding
from app.models.analysis import ContentChunk, SimilarityFindingType


def _chunk(chunk_id: str, page_url: str, text: str) -> ContentChunk:
    return ContentChunk(
        chunk_id=chunk_id,
        page_url=page_url,
        page_title="Example",
        page_h1="Example",
        section_id="section-000",
        section_path=["Example"],
        section_heading="Example",
        section_heading_level=1,
        chunk_text=text,
        chunk_order=0,
        token_estimate=max(1, len(text) // 4),
        text_length=len(text),
    )


def test_detect_cross_page_near_duplicate_chunks():
    source_text = (
        "Our website audit service reviews service pages for clarity, trust "
        "signals, customer proof, pricing explanations, and stronger calls to "
        "action so buyers understand the next step before contacting sales."
    )
    matched_text = (
        "This website audit service reviews service pages for clarity, trust "
        "signals, customer proof, pricing explanations, and stronger calls to "
        "action before buyers decide whether to contact sales."
    )
    source = _chunk("a", "https://example.com/services", source_text)
    matched = _chunk("b", "https://example.com/pricing", matched_text)
    embeddings = [
        build_chunk_embedding(source, [1.0, 0.0]),
        build_chunk_embedding(matched, [0.99, 0.02]),
    ]

    findings = detect_cross_page_duplicates([source, matched], embeddings)

    assert len(findings) == 1
    assert findings[0].finding_type == SimilarityFindingType.NEAR_DUPLICATE
    assert findings[0].source_chunk.chunk_id == "a"
    assert findings[0].matched_chunk.chunk_id == "b"
    assert findings[0].similarity_score > 0.92


def test_detect_cross_page_content_overlap_with_lower_similarity():
    source_text = (
        "The content audit workflow reviews page clarity, heading structure, "
        "calls to action, customer proof, and trust signals for website teams "
        "that need better recommendations before launch."
    )
    matched_text = (
        "Our review process checks page clarity, heading structure, calls to "
        "action, trust signals, and customer proof so website teams can improve "
        "recommendations before launch."
    )
    source = _chunk("a", "https://example.com/about", source_text)
    matched = _chunk("b", "https://example.com/features", matched_text)
    embeddings = [
        build_chunk_embedding(source, [1.0, 0.0]),
        build_chunk_embedding(matched, [0.86, 0.5]),
    ]

    findings = detect_cross_page_duplicates([source, matched], embeddings)

    assert len(findings) == 1
    assert findings[0].finding_type == SimilarityFindingType.CONTENT_OVERLAP


def test_duplicate_detector_does_not_flag_same_page_matches_by_default():
    text = (
        "The audit workflow reviews clarity, calls to action, proof, pricing "
        "details, and trust signals for website pages before publishing."
    )
    first = _chunk("a", "https://example.com/services", text)
    second = _chunk("b", "https://example.com/services", text)
    embeddings = [
        build_chunk_embedding(first, [1.0, 0.0]),
        build_chunk_embedding(second, [1.0, 0.0]),
    ]

    findings = detect_cross_page_duplicates([first, second], embeddings)

    assert findings == []


def test_duplicate_detector_does_not_flag_dissimilar_low_overlap_chunks():
    source = _chunk(
        "a",
        "https://example.com/services",
        (
            "Our website audit service reviews clarity, structure, customer "
            "proof, pricing explanations, and stronger conversion messaging "
            "for teams improving service pages."
        ),
    )
    matched = _chunk(
        "b",
        "https://example.com/blog",
        (
            "The company picnic included lunch, music, team photos, outdoor "
            "games, employee awards, and a recap of volunteer activities from "
            "the previous quarter."
        ),
    )
    embeddings = [
        build_chunk_embedding(source, [1.0, 0.0]),
        build_chunk_embedding(matched, [0.99, 0.01]),
    ]

    findings = detect_cross_page_duplicates([source, matched], embeddings)

    assert findings == []


def test_duplicate_detector_ignores_tiny_chunks_even_with_high_similarity():
    source = _chunk("a", "https://example.com/services", "Contact us today.")
    matched = _chunk("b", "https://example.com/pricing", "Contact us today.")
    embeddings = [
        build_chunk_embedding(source, [1.0, 0.0]),
        build_chunk_embedding(matched, [1.0, 0.0]),
    ]

    findings = detect_cross_page_duplicates([source, matched], embeddings)

    assert findings == []

