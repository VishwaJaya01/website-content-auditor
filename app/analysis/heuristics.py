"""Deterministic pre-LLM heuristic analysis for extracted pages."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlsplit

from app.analysis.chunker import chunk_page
from app.models.analysis import ContentChunk, HeuristicSignal, PageHeuristicSummary
from app.models.analysis import SignalSeverity as Severity
from app.models.crawl import ExtractedPage, PageSection
from app.utils.text import normalize_whitespace

THIN_SECTION_CHARS = 120
THIN_PAGE_CHARS = 300
TRUST_SIGNAL_MIN_CHARS = 180
DENSE_SECTION_CHARS = 2200
LONG_PARAGRAPH_CHARS = 700
MIN_MEANINGFUL_SECTIONS = 2

CTA_PATTERNS = {
    "book a demo",
    "buy now",
    "call us",
    "contact us",
    "download",
    "get a quote",
    "get started",
    "request a demo",
    "schedule",
    "sign up",
    "start free",
    "start trial",
    "subscribe",
    "try free",
}
GENERIC_CTA_PHRASES = {
    "click here",
    "get started",
    "learn more",
    "read more",
    "submit",
}
VAGUE_MARKETING_PHRASES = {
    "best-in-class",
    "cutting-edge",
    "end-to-end solutions",
    "game-changing",
    "innovative solutions",
    "next-generation",
    "seamless experience",
    "state-of-the-art",
    "world-class",
}
COMMERCIAL_TERMS = {
    "business",
    "customer",
    "customers",
    "feature",
    "features",
    "plan",
    "plans",
    "pricing",
    "product",
    "products",
    "service",
    "services",
    "solution",
    "solutions",
}
COMMERCIAL_PATH_TERMS = {
    "features",
    "pricing",
    "product",
    "products",
    "service",
    "services",
    "solutions",
}
TRUST_TERMS = {
    "address",
    "award",
    "case study",
    "certified",
    "client",
    "clients",
    "contact",
    "customer",
    "customers",
    "email",
    "guarantee",
    "phone",
    "privacy",
    "client review",
    "client reviews",
    "customer review",
    "customer reviews",
    "secure",
    "testimonial",
    "testimonials",
    "trusted",
    "years",
}
WEAK_HEADING_TEXT = {
    "about",
    "content",
    "features",
    "home",
    "intro",
    "overview",
    "services",
    "solutions",
    "welcome",
}
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def analyze_page_heuristics(
    page: ExtractedPage,
    *,
    chunks: list[ContentChunk] | None = None,
) -> PageHeuristicSummary:
    """Generate deterministic heuristic signals for an extracted page."""

    active_chunks = chunks if chunks is not None else chunk_page(page)
    signals: list[HeuristicSignal] = []
    full_text = _page_text(page)

    signals.extend(_page_structure_signals(page))
    signals.extend(_section_quality_signals(page))
    signals.extend(_chunk_density_signals(active_chunks))
    signals.extend(_cta_signals(page, full_text))
    signals.extend(_trust_signals(page, full_text))
    signals.extend(_vague_language_signals(page, full_text))
    signals.extend(_repetition_signals(page))

    return PageHeuristicSummary(
        page_url=page.url,
        page_title=page.title,
        signals=signals,
        signal_counts=_count_by_signal_type(signals),
        severity_counts=_count_by_severity(signals),
    )


def _page_structure_signals(page: ExtractedPage) -> list[HeuristicSignal]:
    signals: list[HeuristicSignal] = []
    meaningful_sections = [section for section in page.sections if section.text.strip()]

    if page.text_char_count < THIN_PAGE_CHARS:
        signals.append(
            _signal(
                "thin_page",
                page,
                Severity.MEDIUM,
                0.82,
                "Page has very limited extracted text for a useful content audit.",
                evidence=_snippet(_page_text(page)),
                metadata={"text_char_count": page.text_char_count},
            )
        )

    if len(meaningful_sections) < MIN_MEANINGFUL_SECTIONS:
        signals.append(
            _signal(
                "weak_structure",
                page,
                Severity.LOW,
                0.72,
                "Page has very few meaningful sections, which may limit scanability.",
                metadata={"section_count": len(meaningful_sections)},
            )
        )

    return signals


def _section_quality_signals(page: ExtractedPage) -> list[HeuristicSignal]:
    signals: list[HeuristicSignal] = []
    for section in page.sections:
        section_text = normalize_whitespace(section.text)
        if not section_text:
            continue

        if len(section_text) < THIN_SECTION_CHARS:
            signals.append(
                _signal(
                    "thin_section",
                    page,
                    Severity.LOW,
                    0.78,
                    "Section has very little text and may need more context.",
                    section=section,
                    evidence=_snippet(section_text),
                    metadata={"text_length": len(section_text)},
                )
            )

        if len(section_text) > DENSE_SECTION_CHARS:
            signals.append(
                _signal(
                    "dense_section",
                    page,
                    Severity.MEDIUM,
                    0.76,
                    "Section is long and may need clearer substructure.",
                    section=section,
                    evidence=_snippet(section_text),
                    metadata={"text_length": len(section_text)},
                )
            )

        for block in _paragraph_like_blocks(section.text):
            if len(block) > LONG_PARAGRAPH_CHARS:
                signals.append(
                    _signal(
                        "long_paragraph",
                        page,
                        Severity.MEDIUM,
                        0.8,
                        "A paragraph-like block is long and may be hard to scan.",
                        section=section,
                        evidence=_snippet(block),
                        metadata={"paragraph_length": len(block)},
                    )
                )
                break

        heading_text = normalize_whitespace(section.heading_text or "")
        if not heading_text or _is_weak_heading(heading_text):
            signals.append(
                _signal(
                    "weak_heading",
                    page,
                    Severity.LOW,
                    0.7,
                    "Section heading may be missing or too generic.",
                    section=section,
                    evidence=heading_text or None,
                    metadata={"heading_text": heading_text or None},
                )
            )

    return signals


def _chunk_density_signals(chunks: list[ContentChunk]) -> list[HeuristicSignal]:
    signals: list[HeuristicSignal] = []
    for chunk in chunks:
        if "oversized_chunk" in chunk.warnings:
            signals.append(
                HeuristicSignal(
                    signal_type="oversized_chunk",
                    page_url=chunk.page_url,
                    section_id=chunk.section_id,
                    chunk_id=chunk.chunk_id,
                    severity=Severity.MEDIUM,
                    confidence=0.74,
                    message=(
                        "Chunk is still large after splitting and may need smaller "
                        "source sections."
                    ),
                    evidence_snippet=_snippet(chunk.chunk_text),
                    metadata={"text_length": chunk.text_length},
                )
            )
    return signals


def _cta_signals(page: ExtractedPage, full_text: str) -> list[HeuristicSignal]:
    signals: list[HeuristicSignal] = []
    lower_text = full_text.lower()
    commercial = _looks_commercial(page, full_text)

    if commercial and not _has_cta(lower_text):
        signals.append(
            _signal(
                "missing_cta",
                page,
                Severity.MEDIUM,
                0.72,
                "Important-looking commercial page may lack a clear call to action.",
                evidence=_snippet(full_text),
                metadata={"page_kind": "commercial_or_conversion"},
            )
        )

    for phrase in sorted(GENERIC_CTA_PHRASES):
        if phrase in lower_text:
            signals.append(
                _signal(
                    "generic_cta",
                    page,
                    Severity.LOW,
                    0.68,
                    "CTA phrasing appears generic and may need more specific intent.",
                    evidence=phrase,
                    metadata={"phrase": phrase},
                )
            )
            break

    return signals


def _trust_signals(page: ExtractedPage, full_text: str) -> list[HeuristicSignal]:
    if (
        not _looks_commercial(page, full_text)
        or len(full_text) < TRUST_SIGNAL_MIN_CHARS
    ):
        return []

    lower_text = full_text.lower()
    if any(term in lower_text for term in TRUST_TERMS):
        return []

    return [
        _signal(
            "missing_trust_indicators",
            page,
            Severity.MEDIUM,
            0.66,
            (
                "Commercial page mentions offerings but may lack obvious trust "
                "or credibility cues."
            ),
            evidence=_snippet(full_text),
            metadata={"checked_terms": sorted(TRUST_TERMS)},
        )
    ]


def _vague_language_signals(
    page: ExtractedPage,
    full_text: str,
) -> list[HeuristicSignal]:
    lower_text = full_text.lower()
    found_phrases = [
        phrase for phrase in sorted(VAGUE_MARKETING_PHRASES) if phrase in lower_text
    ]
    if not found_phrases:
        return []

    return [
        _signal(
            "vague_marketing_language",
            page,
            Severity.LOW,
            0.7,
            "Page uses broad marketing phrases that may need concrete proof.",
            evidence=found_phrases[0],
            metadata={"phrases": found_phrases},
        )
    ]


def _repetition_signals(page: ExtractedPage) -> list[HeuristicSignal]:
    signals: list[HeuristicSignal] = []
    heading_counts = Counter(
        _normalize_for_repetition(section.heading_text or "")
        for section in page.sections
        if section.heading_text
    )
    repeated_headings = [
        heading for heading, count in heading_counts.items() if heading and count > 1
    ]
    if repeated_headings:
        signals.append(
            _signal(
                "repeated_heading",
                page,
                Severity.LOW,
                0.84,
                "Same heading text appears multiple times on the page.",
                evidence=repeated_headings[0],
                metadata={"headings": repeated_headings},
            )
        )

    repeated_sentences = _repeated_sentences(page)
    if repeated_sentences:
        signals.append(
            _signal(
                "repeated_phrase",
                page,
                Severity.LOW,
                0.76,
                "A sentence or phrase appears repeatedly within the same page.",
                evidence=repeated_sentences[0],
                metadata={"phrases": repeated_sentences[:5]},
            )
        )

    return signals


def _repeated_sentences(page: ExtractedPage) -> list[str]:
    candidates: list[str] = []
    for section in page.sections:
        text = normalize_whitespace(section.text)
        candidates.extend(
            normalize_whitespace(sentence)
            for sentence in SENTENCE_RE.split(text)
            if len(normalize_whitespace(sentence)) >= 45
        )

    counts = Counter(_normalize_for_repetition(sentence) for sentence in candidates)
    repeated_normalized = {
        sentence for sentence, count in counts.items() if sentence and count > 1
    }
    return [
        sentence
        for sentence in candidates
        if _normalize_for_repetition(sentence) in repeated_normalized
    ]


def _paragraph_like_blocks(text: str) -> list[str]:
    normalized_text = text.strip()
    if not normalized_text:
        return []

    paragraph_blocks = [
        normalize_whitespace(block)
        for block in re.split(r"\n\s*\n+", normalized_text)
        if normalize_whitespace(block)
    ]
    if len(paragraph_blocks) > 1:
        return paragraph_blocks
    return [normalize_whitespace(normalized_text)]


def _looks_commercial(page: ExtractedPage, full_text: str) -> bool:
    parsed = urlsplit(page.url)
    path = parsed.path.strip("/").lower()
    path_terms = {segment for segment in path.split("/") if segment}
    if path_terms.intersection(COMMERCIAL_PATH_TERMS):
        return True

    combined_text = " ".join(
        value
        for value in [page.title, page.h1, full_text[:1000]]
        if value
    ).lower()
    return any(term in combined_text for term in COMMERCIAL_TERMS)


def _has_cta(lower_text: str) -> bool:
    return any(pattern in lower_text for pattern in CTA_PATTERNS)


def _is_weak_heading(heading_text: str) -> bool:
    normalized_heading = normalize_whitespace(heading_text).lower()
    return normalized_heading in WEAK_HEADING_TEXT or len(normalized_heading) < 4


def _page_text(page: ExtractedPage) -> str:
    return normalize_whitespace(" ".join(section.text for section in page.sections))


def _normalize_for_repetition(text: str) -> str:
    normalized = normalize_whitespace(text).lower()
    return re.sub(r"[^a-z0-9 ]+", "", normalized)


def _snippet(text: str | None, *, max_chars: int = 220) -> str | None:
    if not text:
        return None
    normalized = normalize_whitespace(text)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def _signal(
    signal_type: str,
    page: ExtractedPage,
    severity: Severity,
    confidence: float,
    message: str,
    *,
    section: PageSection | None = None,
    evidence: str | None = None,
    metadata: dict[str, object] | None = None,
) -> HeuristicSignal:
    return HeuristicSignal(
        signal_type=signal_type,
        page_url=page.url,
        section_id=section.section_id if section else None,
        severity=severity,
        confidence=confidence,
        message=message,
        evidence_snippet=_snippet(evidence),
        metadata=metadata or {},
    )


def _count_by_signal_type(signals: list[HeuristicSignal]) -> dict[str, int]:
    return dict(Counter(signal.signal_type for signal in signals))


def _count_by_severity(signals: list[HeuristicSignal]) -> dict[Severity, int]:
    return dict(Counter(signal.severity for signal in signals))
