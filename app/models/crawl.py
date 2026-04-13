"""Typed models for URL discovery and HTML fetching."""

from enum import StrEnum

from pydantic import BaseModel, Field


class FetchStatus(StrEnum):
    """Possible outcomes for a single HTML fetch attempt."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    NON_HTML = "non_html"
    INVALID_URL = "invalid_url"


class CrawlConfig(BaseModel):
    """Configuration for same-domain crawl discovery."""

    start_url: str
    max_pages: int = Field(default=8, ge=1, le=100)
    max_depth: int = Field(default=2, ge=0, le=10)


class CrawlWarning(BaseModel):
    """Structured warning emitted during crawl discovery."""

    code: str
    message: str
    url: str | None = None
    source_url: str | None = None


class DiscoveredUrl(BaseModel):
    """A normalized URL accepted as a crawl candidate."""

    url: str
    source_url: str | None = None
    depth: int = Field(ge=0)
    priority_score: int = 0
    priority_reason: str = "standard_page"


class LinkFilterResult(BaseModel):
    """Decision returned by link filtering."""

    allowed: bool
    reason: str
    normalized_url: str | None = None


class FetchResult(BaseModel):
    """Structured result from fetching a URL."""

    url: str
    final_url: str | None = None
    status: FetchStatus
    ok: bool
    status_code: int | None = None
    content_type: str | None = None
    html: str | None = None
    error: str | None = None
    elapsed_ms: float | None = None


class PageSection(BaseModel):
    """Heading-aware section extracted from a fetched HTML page."""

    section_id: str
    heading_path: list[str] = Field(default_factory=list)
    heading_level: int | None = Field(default=None, ge=1, le=4)
    heading_text: str | None = None
    text: str
    order: int = Field(ge=0)
    source_selector: str | None = None


class ExtractedPage(BaseModel):
    """Structured visible content extracted from a fetched HTML page."""

    url: str
    final_url: str | None = None
    canonical_url: str | None = None
    title: str | None = None
    h1: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    text_char_count: int = Field(default=0, ge=0)
    sections: list[PageSection] = Field(default_factory=list)
    warnings: list[CrawlWarning] = Field(default_factory=list)


class CrawlResult(BaseModel):
    """Result of same-domain discovery before content extraction."""

    start_url: str
    normalized_start_url: str
    discovered_urls: list[DiscoveredUrl] = Field(default_factory=list)
    fetch_results: list[FetchResult] = Field(default_factory=list)
    warnings: list[CrawlWarning] = Field(default_factory=list)
