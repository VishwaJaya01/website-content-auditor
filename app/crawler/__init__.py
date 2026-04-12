"""Website crawling foundation.

The current crawler package provides URL normalization, link filtering,
same-domain discovery, prioritization, safe HTML fetching, and visible text
extraction. Playwright fallback is intentionally deferred.
"""

from app.crawler.discovery import discover_site, extract_links, score_url_priority
from app.crawler.extractor import extract_html, extract_page
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
    "extract_html",
    "extract_page",
    "filter_link",
    "get_site_root",
    "is_low_value_url",
    "is_non_html_asset_url",
    "normalize_url",
    "path_depth",
    "same_domain",
    "score_url_priority",
]
