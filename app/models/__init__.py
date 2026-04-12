"""Pydantic models used by the API, jobs, and audit pipeline."""

from app.models.api import AnalyzeAcceptedResponse, AnalyzeRequest, ApiErrorResponse
from app.models.crawl import (
    CrawlConfig,
    CrawlResult,
    CrawlWarning,
    DiscoveredUrl,
    FetchResult,
    FetchStatus,
    LinkFilterResult,
)
from app.models.jobs import JobResponse, JobStatus
from app.models.results import (
    AuditResultResponse,
    PageResultSkeleton,
    RecommendationPlaceholder,
)

__all__ = [
    "AnalyzeAcceptedResponse",
    "AnalyzeRequest",
    "ApiErrorResponse",
    "CrawlConfig",
    "CrawlResult",
    "CrawlWarning",
    "DiscoveredUrl",
    "AuditResultResponse",
    "FetchResult",
    "FetchStatus",
    "JobResponse",
    "JobStatus",
    "LinkFilterResult",
    "PageResultSkeleton",
    "RecommendationPlaceholder",
]
