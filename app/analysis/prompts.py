"""Prompt construction for local chunk-level content analysis."""

from __future__ import annotations

import json
from collections.abc import Sequence

from app.models.analysis import (
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
    SimilarChunkMatch,
)
from app.utils.text import normalize_whitespace

MAX_CHUNK_TEXT_CHARS = 5000
MAX_CONTEXT_SNIPPET_CHARS = 420
MAX_HEURISTIC_SIGNALS = 6
MAX_SIMILAR_MATCHES = 3
MAX_DUPLICATE_FINDINGS = 3


def build_chunk_analysis_prompt(
    chunk: ContentChunk,
    *,
    heuristic_signals: Sequence[HeuristicSignal] | None = None,
    similar_matches: Sequence[SimilarChunkMatch] | None = None,
    duplicate_findings: Sequence[DuplicateContentFinding] | None = None,
) -> str:
    """Build a compact, schema-first prompt for one content chunk."""

    relevant_signals = _relevant_heuristic_signals(chunk, heuristic_signals or [])
    prompt_context = {
        "page": {
            "url": chunk.page_url,
            "title": chunk.page_title,
            "h1": chunk.page_h1,
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
        "- Use severity/priority values only from: info, low, medium, high.\n"
        "- Use confidence as a number from 0.0 to 1.0.\n\n"
        "Required JSON schema:\n"
        "{\n"
        '  "chunk_id": "string",\n'
        '  "page_url": "string",\n'
        '  "section_id": "string",\n'
        '  "section_path": ["string"],\n'
        '  "improvements": [\n'
        "    {\n"
        '      "category": '
        '"clarity|grammar|tone|cta|structure|duplication|trust|engagement|other",\n'
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
