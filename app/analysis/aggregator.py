"""Aggregate chunk, heuristic, and duplicate findings into final audit output."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.models.analysis import (
    ChunkAnalysisResult,
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
    ImprovementRecommendation,
    MissingContentRecommendation,
)
from app.models.crawl import ExtractedPage
from app.models.jobs import JobStatus
from app.models.results import (
    AuditResultResponse,
    AuditSummary,
    DuplicateWarning,
    FailedPageRecord,
    PageAuditResult,
)
from app.utils.text import normalize_whitespace

MAX_PAGE_IMPROVEMENTS = 12
MAX_PAGE_MISSING_CONTENT = 8
MAX_PAGE_DUPLICATE_WARNINGS = 6
MAX_TOP_PRIORITIES = 8
PRIORITY_PAGE_TYPE_BONUSES = {
    "homepage": 8.0,
    "pricing": 7.0,
    "services_product": 6.5,
    "contact": 4.0,
    "about": 3.0,
    "faq": 2.5,
    "docs": 2.5,
}
PRIORITY_CATEGORY_BONUSES = {
    "cta": 7.0,
    "trust": 6.0,
    "missing_context": 4.5,
    "clarity": 3.0,
    "structure": 3.0,
    "readability": 2.5,
    "duplication": 2.0,
    "engagement": 2.0,
}
HEURISTIC_SUPPORT_BY_CATEGORY = {
    "cta": {"missing_cta", "generic_cta"},
    "trust": {"missing_trust_indicators", "vague_marketing_language"},
    "missing_context": {"thin_page", "thin_section", "weak_structure"},
    "clarity": {"weak_heading", "vague_marketing_language"},
    "structure": {"weak_structure", "dense_section", "oversized_chunk"},
    "readability": {"long_paragraph", "dense_section", "oversized_chunk"},
    "duplication": {"repeated_heading", "repeated_phrase"},
}


def aggregate_audit_result(
    *,
    job_id: str,
    status: JobStatus,
    input_url: str,
    normalized_url: str,
    pages: list[ExtractedPage],
    chunks: list[ContentChunk],
    heuristic_signals: list[HeuristicSignal],
    duplicate_findings: list[DuplicateContentFinding],
    chunk_results: list[ChunkAnalysisResult],
    failed_pages: list[FailedPageRecord] | None = None,
    warnings: list[str] | None = None,
) -> AuditResultResponse:
    """Build the final grouped JSON result for one audit job."""

    chunks_by_page = _group_chunks_by_page(chunks)
    signals_by_page = _group_signals_by_page(heuristic_signals)
    chunk_results_by_page = _group_chunk_results_by_page(chunk_results)
    duplicates_by_page = _group_duplicates_by_page(duplicate_findings)

    page_results = [
        _aggregate_page(
            page,
            page_chunks=chunks_by_page.get(page.url, []),
            heuristic_signals=signals_by_page.get(page.url, []),
            duplicate_findings=duplicates_by_page.get(page.url, []),
            chunk_results=chunk_results_by_page.get(page.url, []),
        )
        for page in pages
    ]

    summary = AuditSummary(
        pages_analyzed=len(page_results),
        pages_failed=len(failed_pages or []),
        chunks_analyzed=len(chunks),
        improvements_count=sum(
            len(page.improvement_recommendations) for page in page_results
        ),
        missing_content_count=sum(
            len(page.missing_content_recommendations) for page in page_results
        ),
        duplicate_findings_count=len(duplicate_findings),
        heuristic_signals_count=len(heuristic_signals),
    )

    return AuditResultResponse(
        job_id=job_id,
        status=status,
        message=_result_message(status, summary),
        input_url=input_url,
        normalized_url=normalized_url,
        generated_at=datetime.now(UTC),
        summary=summary,
        top_priorities=_build_top_priorities(page_results),
        pages=page_results,
        failed_pages=failed_pages or [],
        warnings=warnings or [],
    )


def classify_page_type(page: ExtractedPage) -> str:
    """Classify a page type with simple URL/title/H1 heuristics."""

    parsed = urlsplit(page.url)
    path = parsed.path.strip("/").lower()
    path_segments = {segment for segment in path.split("/") if segment}
    fallback_haystack = " ".join(
        value for value in [page.title, page.h1] if value
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


def _aggregate_page(
    page: ExtractedPage,
    *,
    page_chunks: list[ContentChunk],
    heuristic_signals: list[HeuristicSignal],
    duplicate_findings: list[DuplicateContentFinding],
    chunk_results: list[ChunkAnalysisResult],
) -> PageAuditResult:
    improvements = _dedupe_improvements(
        [
            recommendation
            for result in chunk_results
            for recommendation in result.improvements
        ]
    )
    missing_content = _dedupe_missing_content(
        [
            recommendation
            for result in chunk_results
            for recommendation in result.missing_content
        ]
    )
    chunk_warnings = [
        warning
        for result in chunk_results
        for warning in result.warnings
    ]

    heuristic_counts = Counter(signal.signal_type for signal in heuristic_signals)
    duplicate_warnings = [
        _duplicate_warning(finding, current_page_url=page.url)
        for finding in duplicate_findings
    ]

    return PageAuditResult(
        url=page.url,
        title=page.title,
        page_type=classify_page_type(page),
        summary=_page_summary(page, improvements, missing_content, heuristic_counts),
        sections_analyzed=len(page.sections),
        chunks_analyzed=len(page_chunks),
        improvement_recommendations=improvements[:MAX_PAGE_IMPROVEMENTS],
        missing_content_recommendations=missing_content[:MAX_PAGE_MISSING_CONTENT],
        duplicate_warnings=duplicate_warnings[:MAX_PAGE_DUPLICATE_WARNINGS],
        heuristic_signal_summary=dict(heuristic_counts),
        extraction_warnings=[warning.message for warning in page.warnings],
        warnings=chunk_warnings,
    )


def _dedupe_improvements(
    recommendations: list[ImprovementRecommendation],
) -> list[ImprovementRecommendation]:
    best_by_key: dict[str, ImprovementRecommendation] = {}
    for recommendation in recommendations:
        key = _dedupe_key(
            recommendation.category,
            recommendation.issue,
            recommendation.suggested_change,
        )
        current = best_by_key.get(key)
        if current is None or recommendation.confidence > current.confidence:
            best_by_key[key] = recommendation
    return sorted(
        best_by_key.values(),
        key=lambda item: (_severity_rank(item.severity.value), item.confidence),
        reverse=True,
    )


def _dedupe_missing_content(
    recommendations: list[MissingContentRecommendation],
) -> list[MissingContentRecommendation]:
    best_by_key: dict[str, MissingContentRecommendation] = {}
    for recommendation in recommendations:
        key = _dedupe_key(
            recommendation.missing_content,
            recommendation.suggestion_or_outline,
        )
        current = best_by_key.get(key)
        if current is None or recommendation.confidence > current.confidence:
            best_by_key[key] = recommendation
    return sorted(
        best_by_key.values(),
        key=lambda item: (_severity_rank(item.priority.value), item.confidence),
        reverse=True,
    )


def _duplicate_warning(
    finding: DuplicateContentFinding,
    *,
    current_page_url: str,
) -> DuplicateWarning:
    matched_chunk = (
        finding.matched_chunk
        if finding.source_chunk.page_url == current_page_url
        else finding.source_chunk
    )
    return DuplicateWarning(
        finding_type=finding.finding_type.value,
        source_chunk_id=finding.source_chunk.chunk_id,
        matched_chunk_id=matched_chunk.chunk_id,
        matched_page_url=matched_chunk.page_url,
        similarity_score=finding.similarity_score,
        message=finding.message,
        evidence_snippet=finding.evidence_snippet,
    )


def _build_top_priorities(page_results: list[PageAuditResult]) -> list[dict[str, Any]]:
    priorities: list[dict[str, Any]] = []
    for page in page_results:
        for recommendation in page.improvement_recommendations:
            if recommendation.severity.value in {"high", "medium"}:
                category = recommendation.category.value
                priority_score, why_prioritized = _score_recommendation_priority(
                    page,
                    severity=recommendation.severity.value,
                    confidence=recommendation.confidence,
                    category=category,
                )
                priorities.append(
                    {
                        "type": "improvement",
                        "page_url": page.url,
                        "category": category,
                        "severity": recommendation.severity.value,
                        "confidence": recommendation.confidence,
                        "priority_score": priority_score,
                        "why_prioritized": why_prioritized,
                        "issue": recommendation.issue,
                        "suggested_change": recommendation.suggested_change,
                    }
                )
        for recommendation in page.missing_content_recommendations:
            if recommendation.priority.value in {"high", "medium"}:
                priority_score, why_prioritized = _score_recommendation_priority(
                    page,
                    severity=recommendation.priority.value,
                    confidence=recommendation.confidence,
                    category=_missing_content_priority_category(recommendation),
                )
                priorities.append(
                    {
                        "type": "missing_content",
                        "page_url": page.url,
                        "priority": recommendation.priority.value,
                        "confidence": recommendation.confidence,
                        "priority_score": priority_score,
                        "why_prioritized": why_prioritized,
                        "missing_content": recommendation.missing_content,
                        "suggestion": recommendation.suggestion_or_outline,
                    }
                )
        for warning in page.duplicate_warnings:
            priority_score, why_prioritized = _score_duplicate_priority(page, warning)
            priorities.append(
                {
                    "type": "duplicate_content",
                    "page_url": page.url,
                    "severity": "medium",
                    "confidence": warning.similarity_score,
                    "priority_score": priority_score,
                    "why_prioritized": why_prioritized,
                    "issue": warning.message,
                }
            )

    priorities.sort(
        key=lambda item: (
            float(item.get("priority_score") or 0.0),
            _severity_rank(str(item.get("severity") or item.get("priority") or "low")),
            float(item.get("confidence") or 0.0),
        ),
        reverse=True,
    )
    return priorities[:MAX_TOP_PRIORITIES]


def _score_recommendation_priority(
    page: PageAuditResult,
    *,
    severity: str,
    confidence: float,
    category: str,
) -> tuple[float, str]:
    severity_points = {
        "high": 64.0,
        "medium": 44.0,
        "low": 24.0,
        "info": 10.0,
    }.get(severity, 10.0)
    page_type_bonus = PRIORITY_PAGE_TYPE_BONUSES.get(page.page_type, 0.0)
    category_bonus = PRIORITY_CATEGORY_BONUSES.get(category, 1.0)
    supported_signals = _supporting_heuristics(page, category)
    heuristic_bonus = min(len(supported_signals) * 4.0, 8.0)
    score = min(
        100.0,
        severity_points
        + (confidence * 12.0)
        + page_type_bonus
        + category_bonus
        + heuristic_bonus,
    )

    reasons = [f"{severity} severity", f"{confidence:.2f} confidence"]
    if page_type_bonus:
        reasons.append(f"{page.page_type.replace('_', '/')} page")
    if category_bonus >= 4.0:
        reasons.append(f"{category.replace('_', ' ')} issue")
    if supported_signals:
        reasons.append(
            "supported by heuristic signal"
            if len(supported_signals) == 1
            else "supported by heuristic signals"
        )
    return round(score, 1), "; ".join(reasons) + "."


def _score_duplicate_priority(
    page: PageAuditResult,
    warning: DuplicateWarning,
) -> tuple[float, str]:
    page_type_bonus = PRIORITY_PAGE_TYPE_BONUSES.get(page.page_type, 0.0)
    score = min(100.0, 42.0 + (warning.similarity_score * 26.0) + page_type_bonus)
    reasons = [
        "cross-page overlap",
        f"{warning.similarity_score:.2f} similarity",
    ]
    if page_type_bonus:
        reasons.append(f"{page.page_type.replace('_', '/')} page")
    return round(score, 1), "; ".join(reasons) + "."


def _missing_content_priority_category(
    recommendation: MissingContentRecommendation,
) -> str:
    haystack = (
        f"{recommendation.missing_content} "
        f"{recommendation.suggestion_or_outline} "
        f"{recommendation.reason}"
    ).lower()
    if any(term in haystack for term in ("cta", "call to action", "next step")):
        return "cta"
    if any(
        term in haystack
        for term in (
            "trust",
            "proof",
            "testimonial",
            "review",
            "case study",
            "customer",
            "credibility",
        )
    ):
        return "trust"
    return "missing_context"


def _supporting_heuristics(page: PageAuditResult, category: str) -> set[str]:
    expected_signals = HEURISTIC_SUPPORT_BY_CATEGORY.get(category, set())
    return {
        signal_type
        for signal_type, count in page.heuristic_signal_summary.items()
        if count > 0 and signal_type in expected_signals
    }


def _page_summary(
    page: ExtractedPage,
    improvements: list[ImprovementRecommendation],
    missing_content: list[MissingContentRecommendation],
    heuristic_counts: Counter[str],
) -> str:
    parts = [
        f"{len(page.sections)} sections",
        f"{len(improvements)} improvements",
        f"{len(missing_content)} missing-content suggestions",
    ]
    if heuristic_counts:
        most_common_signal, count = heuristic_counts.most_common(1)[0]
        parts.append(f"top heuristic: {most_common_signal} ({count})")
    return "; ".join(parts) + "."


def _group_chunks_by_page(chunks: list[ContentChunk]) -> dict[str, list[ContentChunk]]:
    grouped: dict[str, list[ContentChunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.page_url].append(chunk)
    return grouped


def _group_signals_by_page(
    signals: list[HeuristicSignal],
) -> dict[str, list[HeuristicSignal]]:
    grouped: dict[str, list[HeuristicSignal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.page_url].append(signal)
    return grouped


def _group_chunk_results_by_page(
    chunk_results: list[ChunkAnalysisResult],
) -> dict[str, list[ChunkAnalysisResult]]:
    grouped: dict[str, list[ChunkAnalysisResult]] = defaultdict(list)
    for result in chunk_results:
        grouped[result.page_url].append(result)
    return grouped


def _group_duplicates_by_page(
    findings: list[DuplicateContentFinding],
) -> dict[str, list[DuplicateContentFinding]]:
    grouped: dict[str, list[DuplicateContentFinding]] = defaultdict(list)
    for finding in findings:
        grouped[finding.source_chunk.page_url].append(finding)
        grouped[finding.matched_chunk.page_url].append(finding)
    return grouped


def _dedupe_key(*values: str) -> str:
    return "|".join(normalize_whitespace(value).lower() for value in values)


def _severity_rank(value: str) -> int:
    return {"high": 4, "medium": 3, "low": 2, "info": 1}.get(value, 0)


def _result_message(status: JobStatus, summary: AuditSummary) -> str:
    if status == JobStatus.COMPLETED:
        return "Audit completed successfully."
    if status == JobStatus.PARTIAL:
        return "Audit completed with partial results and warnings."
    if summary.pages_analyzed:
        return "Audit produced usable results with warnings."
    return "Audit did not produce usable results."
