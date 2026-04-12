"""Tests for page/site-level aggregation."""

from app.analysis.aggregator import aggregate_audit_result, classify_page_type
from app.models.analysis import (
    ChunkAnalysisResult,
    ContentChunk,
    ImprovementRecommendation,
    MissingContentRecommendation,
    SignalSeverity,
)
from app.models.crawl import ExtractedPage, PageSection
from app.models.jobs import JobStatus


def _page(url: str = "https://example.com/pricing") -> ExtractedPage:
    return ExtractedPage(
        url=url,
        title="Pricing",
        h1="Simple pricing",
        text_char_count=220,
        sections=[
            PageSection(
                section_id="section-000",
                heading_path=["Simple pricing"],
                heading_level=1,
                heading_text="Simple pricing",
                text="Pricing plans for teams that need clearer content audits.",
                order=0,
            )
        ],
    )


def _chunk(page: ExtractedPage) -> ContentChunk:
    return ContentChunk(
        chunk_id="chunk-001",
        page_url=page.url,
        page_title=page.title,
        page_h1=page.h1,
        section_id="section-000",
        section_path=["Simple pricing"],
        section_heading="Simple pricing",
        section_heading_level=1,
        chunk_text=page.sections[0].text,
        chunk_order=0,
        token_estimate=20,
        text_length=len(page.sections[0].text),
    )


def test_aggregate_audit_result_groups_and_deduplicates_recommendations():
    page = _page()
    chunk = _chunk(page)
    duplicate_recommendation = ImprovementRecommendation(
        category="cta",
        page_url=page.url,
        section_id=chunk.section_id,
        section_path=chunk.section_path,
        issue="The pricing section lacks a clear next step.",
        suggested_change="Add a specific CTA after the plan explanation.",
        reason="A clear next step helps visitors act.",
        severity=SignalSeverity.MEDIUM,
        confidence=0.7,
        evidence_snippet="Pricing plans for teams",
    )
    stronger_duplicate = duplicate_recommendation.model_copy(
        update={"confidence": 0.9}
    )
    missing = MissingContentRecommendation(
        page_url=page.url,
        section_id=chunk.section_id,
        section_path=chunk.section_path,
        missing_content="Plan comparison details",
        suggestion_or_outline="Add a short table comparing included audit features.",
        reason="Comparison details reduce pricing confusion.",
        priority=SignalSeverity.MEDIUM,
        confidence=0.8,
    )

    result = aggregate_audit_result(
        job_id="job-1",
        status=JobStatus.COMPLETED,
        input_url=page.url,
        normalized_url=page.url,
        pages=[page],
        chunks=[chunk],
        heuristic_signals=[],
        duplicate_findings=[],
        chunk_results=[
            ChunkAnalysisResult(
                chunk_id=chunk.chunk_id,
                page_url=page.url,
                section_id=chunk.section_id,
                section_path=chunk.section_path,
                improvements=[duplicate_recommendation, stronger_duplicate],
                missing_content=[missing],
            )
        ],
    )

    assert result.summary.pages_analyzed == 1
    assert result.summary.improvements_count == 1
    assert result.pages[0].page_type == "pricing"
    assert result.pages[0].improvement_recommendations[0].confidence == 0.9
    assert result.pages[0].missing_content_recommendations[0].missing_content
    assert result.top_priorities


def test_classify_page_type_uses_url_title_and_h1():
    assert classify_page_type(_page("https://example.com/")) == "homepage"
    assert classify_page_type(_page("https://example.com/about")) == "about"
    assert classify_page_type(_page("https://example.com/services")) == (
        "services_product"
    )
