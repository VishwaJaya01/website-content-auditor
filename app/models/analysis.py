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

