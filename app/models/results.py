"""Public result models for completed website audits."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.analysis import (
    ImprovementRecommendation,
    MissingContentRecommendation,
)
from app.models.jobs import JobStatus


class RecommendationPlaceholder(BaseModel):
    """Legacy-compatible minimal recommendation shape."""

    category: str
    issue: str
    suggested_change: str
    reason: str
    severity: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class AuditSummary(BaseModel):
    """Site-level summary counts for an audit result."""

    pages_analyzed: int = 0
    pages_failed: int = 0
    chunks_analyzed: int = 0
    improvements_count: int = 0
    missing_content_count: int = 0
    duplicate_findings_count: int = 0
    heuristic_signals_count: int = 0


class FailedPageRecord(BaseModel):
    """Page-level failure captured during crawling, fetching, or extraction."""

    url: str
    reason: str
    stage: str


class DuplicateWarning(BaseModel):
    """Compact duplicate/overlap warning for page-level output."""

    finding_type: str
    source_chunk_id: str
    matched_chunk_id: str
    matched_page_url: str
    similarity_score: float
    message: str
    evidence_snippet: str | None = None


class PageAuditResult(BaseModel):
    """Page-level grouped audit output."""

    url: str
    title: str | None = None
    page_type: str = "generic"
    summary: str
    sections_analyzed: int = 0
    chunks_analyzed: int = 0
    improvement_recommendations: list[ImprovementRecommendation] = Field(
        default_factory=list
    )
    missing_content_recommendations: list[MissingContentRecommendation] = Field(
        default_factory=list
    )
    duplicate_warnings: list[DuplicateWarning] = Field(default_factory=list)
    heuristic_signal_summary: dict[str, int] = Field(default_factory=dict)
    extraction_warnings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PageResultSkeleton(PageAuditResult):
    """Backward-compatible alias for earlier scaffold result tests."""


class AuditResultResponse(BaseModel):
    """Public response shape for audit results."""

    job_id: str
    status: JobStatus
    message: str
    input_url: str | None = None
    normalized_url: str | None = None
    generated_at: datetime | None = None
    summary: AuditSummary = Field(default_factory=AuditSummary)
    top_priorities: list[dict[str, Any]] = Field(default_factory=list)
    pages: list[PageAuditResult] = Field(default_factory=list)
    failed_pages: list[FailedPageRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

