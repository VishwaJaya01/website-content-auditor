"""Typed models for chunking and lightweight heuristic analysis."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SignalSeverity(StrEnum):
    """Severity values used by deterministic heuristic signals."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SimilarityFindingType(StrEnum):
    """Types of similarity findings produced before LLM analysis."""

    NEAR_DUPLICATE = "near_duplicate"
    CONTENT_OVERLAP = "content_overlap"


class ContentChunk(BaseModel):
    """Section-aware chunk prepared for later embedding or LLM analysis."""

    chunk_id: str
    page_url: str
    page_title: str | None = None
    page_h1: str | None = None
    section_id: str
    section_path: list[str] = Field(default_factory=list)
    section_heading: str | None = None
    section_heading_level: int | None = Field(default=None, ge=1, le=4)
    chunk_text: str
    chunk_order: int = Field(ge=0)
    token_estimate: int = Field(ge=0)
    text_length: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class ChunkEmbedding(BaseModel):
    """Embedding vector and metadata for a content chunk."""

    chunk_id: str
    page_url: str
    section_id: str
    vector: list[float]
    text_length: int = Field(ge=0)
    token_estimate: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimilarChunkMatch(BaseModel):
    """Structured similarity result between two chunks."""

    query_chunk: ContentChunk
    matched_chunk: ContentChunk
    similarity_score: float = Field(ge=-1.0, le=1.0)
    cross_page: bool


class DuplicateContentFinding(BaseModel):
    """Potential duplicate or overlapping content across chunks."""

    finding_type: SimilarityFindingType
    source_chunk: ContentChunk
    matched_chunk: ContentChunk
    similarity_score: float = Field(ge=-1.0, le=1.0)
    message: str
    evidence_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImprovementRecommendation(BaseModel):
    """LLM-generated recommendation for improving existing content."""

    category: str
    page_url: str
    section_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    issue: str
    suggested_change: str
    example_text: str | None = None
    reason: str
    severity: SignalSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_snippet: str | None = None


class MissingContentRecommendation(BaseModel):
    """LLM-generated recommendation for content that should be added."""

    page_url: str
    section_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    recommended_location: str | None = None
    missing_content: str
    suggestion_or_outline: str
    reason: str
    priority: SignalSeverity
    confidence: float = Field(ge=0.0, le=1.0)


class ChunkAnalysisResult(BaseModel):
    """Validated LLM analysis result for one content chunk."""

    chunk_id: str
    page_url: str
    section_id: str
    section_path: list[str] = Field(default_factory=list)
    improvements: list[ImprovementRecommendation] = Field(default_factory=list)
    missing_content: list[MissingContentRecommendation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class HeuristicSignal(BaseModel):
    """A structured rule-based signal generated before LLM analysis."""

    signal_type: str
    page_url: str
    section_id: str | None = None
    chunk_id: str | None = None
    severity: SignalSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    message: str
    evidence_snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PageHeuristicSummary(BaseModel):
    """Heuristic analysis result for one extracted page."""

    page_url: str
    page_title: str | None = None
    signals: list[HeuristicSignal] = Field(default_factory=list)
    signal_counts: dict[str, int] = Field(default_factory=dict)
    severity_counts: dict[SignalSeverity, int] = Field(default_factory=dict)
