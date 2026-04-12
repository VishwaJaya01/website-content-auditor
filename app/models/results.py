"""Result skeletons for the future audit pipeline."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.jobs import JobStatus


class RecommendationPlaceholder(BaseModel):
    """Minimal recommendation shape reserved for future analysis output."""

    category: str
    issue: str
    suggested_change: str
    reason: str
    severity: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PageResultSkeleton(BaseModel):
    """Lightweight page-level result placeholder."""

    url: str
    title: str | None = None
    page_type: str | None = None
    recommendations: list[RecommendationPlaceholder] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditResultResponse(BaseModel):
    """Public response shape for audit results."""

    job_id: str
    status: JobStatus
    message: str
    generated_at: datetime | None = None
    pages: list[PageResultSkeleton] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

