"""Pydantic models used by the API, jobs, and audit pipeline."""

from app.models.analysis import (
    ChunkAnalysisResult,
    ChunkEmbedding,
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
    ImprovementRecommendation,
    MissingContentRecommendation,
    PageHeuristicSummary,
    RecommendationCategory,
    SignalSeverity,
    SimilarChunkMatch,
    SimilarityFindingType,
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
    "ChunkAnalysisResult",
    "ChunkEmbedding",
    "ContentChunk",
    "CrawlConfig",
    "CrawlResult",
    "CrawlWarning",
    "DiscoveredUrl",
    "DuplicateContentFinding",
    "ExtractedPage",
    "AuditResultResponse",
    "FetchResult",
    "FetchStatus",
    "HeuristicSignal",
    "ImprovementRecommendation",
    "JobResponse",
    "JobStatus",
    "LinkFilterResult",
    "MissingContentRecommendation",
    "PageHeuristicSummary",
    "PageResultSkeleton",
    "PageSection",
    "RecommendationCategory",
    "RecommendationPlaceholder",
    "SignalSeverity",
    "SimilarChunkMatch",
    "SimilarityFindingType",
]
