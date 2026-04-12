"""Practical link filtering rules for same-domain crawling."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit

from app.models.crawl import LinkFilterResult

from .url_normalizer import UrlNormalizationError, normalize_url, same_domain

BLOCKED_SCHEME_PREFIXES = ("mailto:", "tel:", "javascript:")

NON_HTML_EXTENSIONS = {
    ".7z",
    ".avi",
    ".bmp",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".eot",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogg",
    ".otf",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".rss",
    ".svg",
    ".tar",
    ".tif",
    ".tiff",
    ".ttf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}

LOW_VALUE_SEGMENTS = {
    "account",
    "accounts",
    "admin",
    "basket",
    "cart",
    "categories",
    "category",
    "checkout",
    "dashboard",
    "login",
    "log-in",
    "logout",
    "register",
    "search",
    "sign-in",
    "sign-up",
    "signin",
    "signup",
    "tag",
    "tags",
    "user",
    "users",
    "wp-admin",
}

LOW_VALUE_QUERY_KEYS = {"replytocom", "share", "print"}
SEARCH_QUERY_KEYS = {"q", "query", "s"}
MAX_QUERY_PARAMS = 4


def filter_link(
    href: str | None,
    *,
    base_url: str,
    site_root_url: str,
    seen_urls: set[str] | None = None,
) -> LinkFilterResult:
    """Return whether a raw link should be accepted for same-domain crawling."""

    if href is None or not href.strip():
        return LinkFilterResult(allowed=False, reason="empty_link")

    raw_href = href.strip()
    lowered_href = raw_href.lower()
    if raw_href.startswith("#"):
        return LinkFilterResult(allowed=False, reason="fragment_only")
    if lowered_href.startswith(BLOCKED_SCHEME_PREFIXES):
        return LinkFilterResult(allowed=False, reason="blocked_scheme")

    try:
        normalized_url = normalize_url(raw_href, base_url=base_url)
    except UrlNormalizationError:
        return LinkFilterResult(allowed=False, reason="invalid_url")

    if not same_domain(normalized_url, site_root_url):
        return LinkFilterResult(
            allowed=False,
            reason="external_domain",
            normalized_url=normalized_url,
        )
    if is_non_html_asset_url(normalized_url):
        return LinkFilterResult(
            allowed=False,
            reason="non_html_asset",
            normalized_url=normalized_url,
        )
    if is_low_value_url(normalized_url):
        return LinkFilterResult(
            allowed=False,
            reason="low_value_path",
            normalized_url=normalized_url,
        )
    if seen_urls is not None and normalized_url in seen_urls:
        return LinkFilterResult(
            allowed=False,
            reason="duplicate_url",
            normalized_url=normalized_url,
        )

    return LinkFilterResult(
        allowed=True,
        reason="accepted",
        normalized_url=normalized_url,
    )


def is_non_html_asset_url(url: str) -> bool:
    """Return whether a URL path points to an obvious non-HTML asset."""

    path = urlsplit(url).path.lower()
    return any(path.endswith(extension) for extension in NON_HTML_EXTENSIONS)


def is_low_value_url(url: str) -> bool:
    """Return whether a URL is unlikely to contain useful marketing content."""

    parsed = urlsplit(url)
    path_segments = [segment.lower() for segment in parsed.path.split("/") if segment]

    if any(segment in LOW_VALUE_SEGMENTS for segment in path_segments):
        return True
    if _looks_like_pagination(path_segments):
        return True

    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    if len(query_params) > MAX_QUERY_PARAMS:
        return True

    query_keys = {key.lower() for key, _ in query_params}
    if query_keys.intersection(LOW_VALUE_QUERY_KEYS):
        return True
    if "search" in path_segments and query_keys.intersection(SEARCH_QUERY_KEYS):
        return True
    if _has_pagination_query(query_params):
        return True

    return False


def _looks_like_pagination(path_segments: list[str]) -> bool:
    joined_path = "/" + "/".join(path_segments)
    if re.search(r"/page/\d+$", joined_path):
        return True
    if not path_segments:
        return False
    return re.fullmatch(r"p(?:age)?-?\d+", path_segments[-1]) is not None


def _has_pagination_query(query_params: list[tuple[str, str]]) -> bool:
    for key, value in query_params:
        if key.lower() in {"page", "paged"} and value.isdigit() and int(value) > 1:
            return True
    return False
