"""Prompt construction for local chunk-level content analysis."""

from __future__ import annotations

import json
from collections.abc import Sequence
from urllib.parse import urlsplit

from app.models.analysis import (
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
    RecommendationCategory,
    SimilarChunkMatch,
)
from app.utils.text import normalize_whitespace

MAX_CHUNK_TEXT_CHARS = 5000
MAX_CONTEXT_SNIPPET_CHARS = 420
MAX_HEURISTIC_SIGNALS = 6
MAX_SIMILAR_MATCHES = 3
MAX_DUPLICATE_FINDINGS = 3
ALLOWED_CATEGORIES = ", ".join(category.value for category in RecommendationCategory)
PAGE_TYPE_GUIDANCE: dict[str, str] = {
    "homepage": (
        "Focus on value proposition clarity, first-screen trust, audience fit, "
        "navigation clarity, and whether visitors have a clear next action."
    ),
    "pricing": (
        "Focus on plan clarity, included features, objections, reassurance, "
        "comparison details, and the next step after choosing a plan."
    ),
    "services_product": (
        "Focus on benefits, proof, differentiation, process, objections, and "
        "how clearly the product or service outcome is explained."
    ),
    "docs": (
        "Focus on completeness, examples, step order, terminology clarity, "
        "navigation cues, and whether readers can complete the task."
    ),
    "faq": (
        "Focus on question coverage, direct answers, reassurance, and missing "
        "objections that visitors are likely to have."
    ),
    "contact": (
        "Focus on contact clarity, available channels, response expectations, "
        "location or support cues, and reassurance before reaching out."
    ),
    "about": (
        "Focus on credibility, mission, team or story detail, trust signals, "
        "and why visitors should believe the organization."
    ),
    "blog": (
        "Focus on headline clarity, article structure, evidence, freshness, "
        "reader engagement, and useful next reads or actions."
    ),
    "generic": (
        "Focus on clarity, usefulness, structure, trust, and actionability for "
        "the specific page text provided."
    ),
}


def build_chunk_analysis_prompt(
    chunk: ContentChunk,
    *,
    heuristic_signals: Sequence[HeuristicSignal] | None = None,
    similar_matches: Sequence[SimilarChunkMatch] | None = None,
    duplicate_findings: Sequence[DuplicateContentFinding] | None = None,
) -> str:
    """Build a compact, schema-first prompt for one content chunk."""

    relevant_signals = _relevant_heuristic_signals(chunk, heuristic_signals or [])
    page_type = _classify_chunk_page_type(chunk)
    prompt_context = {
        "page": {
            "url": chunk.page_url,
            "title": chunk.page_title,
            "h1": chunk.page_h1,
            "page_type": page_type,
        },
        "section": {
            "id": chunk.section_id,
            "path": chunk.section_path,
            "heading": chunk.section_heading,
            "heading_level": chunk.section_heading_level,
        },
        "chunk": {
            "id": chunk.chunk_id,
            "order": chunk.chunk_order,
            "token_estimate": chunk.token_estimate,
            "text": _truncate(chunk.chunk_text, MAX_CHUNK_TEXT_CHARS),
        },
        "heuristic_signals": [_signal_payload(signal) for signal in relevant_signals],
        "similar_chunks": [
            _similar_match_payload(match)
            for match in list(similar_matches or [])[:MAX_SIMILAR_MATCHES]
        ],
        "duplicate_context": [
            _duplicate_payload(finding)
            for finding in list(duplicate_findings or [])[:MAX_DUPLICATE_FINDINGS]
        ],
    }

    return (
        "You are a careful website content auditor. Analyze only the provided "
        "chunk and its metadata. Use heuristic and duplicate context as hints, "
        "not as proof by itself.\n\n"
        "Return JSON only. Do not wrap it in Markdown. Do not include commentary.\n\n"
        "Task:\n"
        "- Identify concrete improvements to existing text.\n"
        "- Identify missing content that should be added to this page or section.\n"
        "- Make recommendations specific, evidence-based, concise, and actionable.\n"
        "- Avoid generic advice such as 'improve readability' unless you name the "
        "specific issue and suggested change.\n"
        "- Do not invent facts about the company, users, results, pricing, or "
        "claims that are not supported by the provided text.\n"
        "- For each improvement, choose exactly one category from: "
        f"{ALLOWED_CATEGORIES}.\n"
        "- Never copy the full category list into the category field.\n"
        "- Do not recommend changes when the text is already clear and no "
        "specific issue is present.\n"
        "- Use severity/priority values only from: info, low, medium, high.\n"
        "- Use confidence as a number from 0.0 to 1.0.\n\n"
        "Page-type focus:\n"
        f"{_page_type_guidance(page_type)}\n\n"
        "Required JSON schema:\n"
        "{\n"
        '  "chunk_id": "string",\n'
        '  "page_url": "string",\n'
        '  "section_id": "string",\n'
        '  "section_path": ["string"],\n'
        '  "improvements": [\n'
        "    {\n"
        '      "category": "clarity",\n'
        '      "page_url": "string",\n'
        '      "section_id": "string",\n'
        '      "section_path": ["string"],\n'
        '      "issue": "string",\n'
        '      "suggested_change": "string",\n'
        '      "example_text": "string or null",\n'
        '      "reason": "string",\n'
        '      "severity": "info|low|medium|high",\n'
        '      "confidence": 0.0,\n'
        '      "evidence_snippet": "string or null"\n'
        "    }\n"
        "  ],\n"
        '  "missing_content": [\n'
        "    {\n"
        '      "page_url": "string",\n'
        '      "section_id": "string",\n'
        '      "section_path": ["string"],\n'
        '      "recommended_location": "string or null",\n'
        '      "missing_content": "string",\n'
        '      "suggestion_or_outline": "string",\n'
        '      "reason": "string",\n'
        '      "priority": "info|low|medium|high",\n'
        '      "confidence": 0.0\n'
        "    }\n"
        "  ],\n"
        '  "warnings": ["string"]\n'
        "}\n\n"
        "If there are no useful findings, return empty arrays. Do not force a "
        "recommendation.\n\n"
        "Valid example recommendation object:\n"
        "{\n"
        '  "category": "cta",\n'
        '  "issue": "The section describes the offer but does not give a next step.",\n'
        '  "suggested_change": '
        '"Add a short CTA such as \\"Book a content review.\\"",\n'
        '  "example_text": "Book a content review",\n'
        '  "reason": "A clear next step helps interested visitors act.",\n'
        '  "severity": "medium",\n'
        '  "confidence": 0.78,\n'
        '  "evidence_snippet": "the relevant source phrase"\n'
        "}\n\n"
        "Input context JSON:\n"
        f"{json.dumps(prompt_context, ensure_ascii=True, indent=2)}"
    )


def build_json_repair_prompt(
    *,
    invalid_output: str,
    validation_error: str | None = None,
) -> str:
    """Build a bounded repair prompt for malformed or schema-invalid JSON."""

    context = {
        "invalid_output": _truncate(invalid_output, 6000),
        "validation_error": _truncate(validation_error or "", 1200),
    }
    return (
        "Repair the following model output into valid JSON only. Do not add "
        "Markdown or explanations. Preserve the intended recommendations when "
        "possible, but make the result match this top-level shape exactly: "
        '{"chunk_id": "...", "page_url": "...", "section_id": "...", '
        '"section_path": [], "improvements": [], "missing_content": [], '
        '"warnings": []}.\n\n'
        f"{json.dumps(context, ensure_ascii=True, indent=2)}"
    )


def _classify_chunk_page_type(chunk: ContentChunk) -> str:
    parsed = urlsplit(chunk.page_url)
    path = parsed.path.strip("/").lower()
    path_segments = {segment for segment in path.split("/") if segment}
    fallback_haystack = " ".join(
        value for value in [chunk.page_title, chunk.page_h1] if value
    ).lower()

    if path in {"", "home", "index"}:
        return "homepage"
    if "pricing" in path_segments or "plans" in path_segments:
        return "pricing"
    if "about" in path_segments or "team" in path_segments:
        return "about"
    if "contact" in path_segments:
        return "contact"
    if "faq" in path_segments:
        return "faq"
    if "docs" in path_segments or "documentation" in path_segments:
        return "docs"
    if path_segments.intersection({"services", "service", "products", "product"}):
        return "services_product"
    if "blog" in path_segments:
        return "blog"

    if "pricing" in fallback_haystack or "plans" in fallback_haystack:
        return "pricing"
    if "about" in fallback_haystack or "team" in fallback_haystack:
        return "about"
    if "contact" in fallback_haystack:
        return "contact"
    if "faq" in fallback_haystack:
        return "faq"
    if "docs" in fallback_haystack or "documentation" in fallback_haystack:
        return "docs"
    if any(
        term in fallback_haystack
        for term in ("services", "service", "products", "product")
    ):
        return "services_product"
    if "blog" in fallback_haystack:
        return "blog"
    return "generic"


def _page_type_guidance(page_type: str) -> str:
    return PAGE_TYPE_GUIDANCE.get(page_type, PAGE_TYPE_GUIDANCE["generic"])


def _relevant_heuristic_signals(
    chunk: ContentChunk,
    signals: Sequence[HeuristicSignal],
) -> list[HeuristicSignal]:
    relevant: list[HeuristicSignal] = []
    for signal in signals:
        if signal.page_url != chunk.page_url:
            continue
        if signal.chunk_id and signal.chunk_id != chunk.chunk_id:
            continue
        if signal.section_id and signal.section_id != chunk.section_id:
            continue
        relevant.append(signal)
    return relevant[:MAX_HEURISTIC_SIGNALS]


def _signal_payload(signal: HeuristicSignal) -> dict[str, object]:
    return {
        "signal_type": signal.signal_type,
        "severity": signal.severity.value,
        "confidence": signal.confidence,
        "message": signal.message,
        "evidence_snippet": signal.evidence_snippet,
        "metadata": signal.metadata,
    }


def _similar_match_payload(match: SimilarChunkMatch) -> dict[str, object]:
    return {
        "matched_chunk_id": match.matched_chunk.chunk_id,
        "matched_page_url": match.matched_chunk.page_url,
        "matched_section_id": match.matched_chunk.section_id,
        "similarity_score": match.similarity_score,
        "cross_page": match.cross_page,
        "matched_text_snippet": _truncate(
            match.matched_chunk.chunk_text,
            MAX_CONTEXT_SNIPPET_CHARS,
        ),
    }


def _duplicate_payload(finding: DuplicateContentFinding) -> dict[str, object]:
    return {
        "finding_type": finding.finding_type.value,
        "source_chunk_id": finding.source_chunk.chunk_id,
        "matched_chunk_id": finding.matched_chunk.chunk_id,
        "matched_page_url": finding.matched_chunk.page_url,
        "similarity_score": finding.similarity_score,
        "message": finding.message,
        "evidence_snippet": finding.evidence_snippet,
        "matched_evidence_snippet": finding.metadata.get("matched_evidence_snippet"),
    }


def _truncate(text: str | None, max_chars: int) -> str:
    if not text:
        return ""
    normalized = normalize_whitespace(text)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."
