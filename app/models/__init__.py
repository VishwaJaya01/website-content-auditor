"""Pydantic models used by the API, jobs, and audit pipeline."""

from app.models.analysis import (
    ContentChunk,
    HeuristicSignal,
    PageHeuristicSummary,
    SignalSeverity,
)
from app.models.api import AnalyzeAcceptedResponse, AnalyzeRequest, ApiErrorResponse
from app.models.crawl import (
    CrawlConfig,
    CrawlResult,
    CrawlWarning,
    DiscoveredUrl,
    ExtractedPage,
    FetchResult,
    FetchStatus,
    LinkFilterResult,
    PageSection,
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
    "ContentChunk",
    "CrawlConfig",
    "CrawlResult",
    "CrawlWarning",
    "DiscoveredUrl",
    "ExtractedPage",
    "AuditResultResponse",
    "FetchResult",
    "FetchStatus",
    "HeuristicSignal",
    "JobResponse",
    "JobStatus",
    "LinkFilterResult",
    "PageHeuristicSummary",
    "PageResultSkeleton",
    "PageSection",
    "RecommendationPlaceholder",
    "SignalSeverity",
]
