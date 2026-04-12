"""Website crawling foundation.

The current crawler package provides URL normalization, link filtering,
same-domain discovery, prioritization, and safe HTML fetching. Visible text
extraction and Playwright fallback are intentionally deferred.
"""

from app.crawler.discovery import discover_site, extract_links, score_url_priority
from app.crawler.fetcher import HttpxHtmlFetcher
from app.crawler.filters import filter_link, is_low_value_url, is_non_html_asset_url
from app.crawler.url_normalizer import (
    UrlNormalizationError,
    canonical_url_equal,
    get_site_root,
    normalize_url,
    path_depth,
    same_domain,
)

__all__ = [
    "HttpxHtmlFetcher",
    "UrlNormalizationError",
    "canonical_url_equal",
    "discover_site",
    "extract_links",
    "filter_link",
    "get_site_root",
    "is_low_value_url",
    "is_non_html_asset_url",
    "normalize_url",
    "path_depth",
    "same_domain",
    "score_url_priority",
]
