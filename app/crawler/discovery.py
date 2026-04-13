"""Same-domain URL discovery and prioritization."""

from __future__ import annotations

from heapq import heappop, heappush
from itertools import count
from typing import Protocol
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from app.config import Settings, get_settings
from app.models.crawl import (
    CrawlResult,
    CrawlWarning,
    DiscoveredUrl,
    FetchResult,
)

from .fetcher import HttpxHtmlFetcher
from .filters import filter_link
from .url_normalizer import UrlNormalizationError, get_site_root, normalize_url

IMPORTANT_PATH_KEYWORDS: dict[str, int] = {
    "pricing": 120,
    "about": 110,
    "service": 105,
    "services": 105,
    "product": 100,
    "products": 100,
    "features": 95,
    "docs": 90,
    "documentation": 90,
    "faq": 85,
    "testimonials": 80,
    "case-studies": 75,
    "contact": 70,
    "blog": 45,
}
HOMEPAGE_PRIORITY = 1000


class HtmlFetcher(Protocol):
    """Minimal fetcher contract used by discovery."""

    def fetch(self, url: str) -> FetchResult:
        """Fetch a URL and return a structured result."""


def discover_site(
    start_url: str,
    *,
    max_pages: int | None = None,
    max_depth: int | None = None,
    fetcher: HtmlFetcher | None = None,
    settings: Settings | None = None,
) -> CrawlResult:
    """Discover prioritized same-domain URLs without extracting visible text."""

    active_settings = settings or get_settings()
    effective_max_pages = max_pages or active_settings.default_max_pages
    effective_max_depth = max_depth or active_settings.default_max_depth

    warnings: list[CrawlWarning] = []
    try:
        normalized_start_url = normalize_url(start_url)
        site_root_url = get_site_root(normalized_start_url)
    except UrlNormalizationError as exc:
        return CrawlResult(
            start_url=start_url,
            normalized_start_url="",
            warnings=[
                CrawlWarning(
                    code="invalid_start_url",
                    message=str(exc),
                    url=start_url,
                )
            ],
        )

    active_fetcher = fetcher or HttpxHtmlFetcher(settings=active_settings)
    seen_urls: set[str] = set()
    discovered_urls: list[DiscoveredUrl] = []
    fetch_results: list[FetchResult] = []
    frontier: list[tuple[int, int, int, DiscoveredUrl]] = []
    insertion_order = count()

    def enqueue(
        url: str,
        *,
        source_url: str | None,
        depth: int,
        priority_override: int | None = None,
        reason_override: str | None = None,
    ) -> None:
        if url in seen_urls or depth > effective_max_depth:
            return
        seen_urls.add(url)
        priority_score, priority_reason = score_url_priority(url, site_root_url)
        if priority_override is not None:
            priority_score = priority_override
        if reason_override is not None:
            priority_reason = reason_override
        candidate = DiscoveredUrl(
            url=url,
            source_url=source_url,
            depth=depth,
            priority_score=priority_score,
            priority_reason=priority_reason,
        )
        heappush(
            frontier,
            (depth, -priority_score, next(insertion_order), candidate),
        )

    if normalized_start_url != site_root_url:
        enqueue(
            normalized_start_url,
            source_url=None,
            depth=0,
            priority_override=HOMEPAGE_PRIORITY + 1,
            reason_override="submitted_start_url",
        )
    enqueue(site_root_url, source_url=None, depth=0)

    while frontier and len(discovered_urls) < effective_max_pages:
        _, _, _, candidate = heappop(frontier)
        discovered_urls.append(candidate)

        fetch_result = active_fetcher.fetch(candidate.url)
        fetch_results.append(fetch_result)
        if not fetch_result.ok:
            warnings.append(
                CrawlWarning(
                    code=fetch_result.status.value,
                    message=fetch_result.error or "Fetch failed.",
                    url=candidate.url,
                    source_url=candidate.source_url,
                )
            )
            continue

        if candidate.depth >= effective_max_depth:
            continue

        for href in extract_links(fetch_result.html or ""):
            decision = filter_link(
                href,
                base_url=fetch_result.final_url or candidate.url,
                site_root_url=site_root_url,
                seen_urls=seen_urls,
            )
            if not decision.allowed or decision.normalized_url is None:
                continue
            enqueue(
                decision.normalized_url,
                source_url=candidate.url,
                depth=candidate.depth + 1,
            )

    return CrawlResult(
        start_url=start_url,
        normalized_start_url=normalized_start_url,
        discovered_urls=discovered_urls,
        fetch_results=fetch_results,
        warnings=warnings,
    )


def extract_links(html: str) -> list[str]:
    """Extract raw href values from anchor tags only."""

    soup = BeautifulSoup(html, "html.parser")
    return [
        href
        for anchor in soup.find_all("a", href=True)
        if (href := anchor.get("href"))
    ]


def score_url_priority(url: str, site_root_url: str) -> tuple[int, str]:
    """Return an explainable priority score for a normalized URL."""

    if normalize_url(url) == normalize_url(site_root_url):
        return HOMEPAGE_PRIORITY, "homepage"

    parsed = urlsplit(url)
    path = parsed.path.strip("/").lower()
    path_segments = [segment for segment in path.split("/") if segment]
    matched_keywords = [
        (keyword, weight)
        for keyword, weight in IMPORTANT_PATH_KEYWORDS.items()
        if keyword in path_segments or keyword in path
    ]

    base_score = 10
    reason = "standard_page"
    if matched_keywords:
        keyword, weight = max(matched_keywords, key=lambda item: item[1])
        base_score += weight
        reason = f"important_path:{keyword}"

    depth_penalty = max(len(path_segments) - 1, 0) * 8
    query_penalty = 10 if parsed.query else 0
    return max(base_score - depth_penalty - query_penalty, 0), reason
