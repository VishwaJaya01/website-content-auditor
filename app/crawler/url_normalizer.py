"""Reusable URL normalization helpers for crawling and cache keys."""

from __future__ import annotations

import re
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)

TRACKING_PARAM_NAMES = {
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "igshid",
}
BLOCKED_SCHEME_PREFIXES = ("mailto:", "tel:", "javascript:")
DEFAULT_SCHEME = "https"


class UrlNormalizationError(ValueError):
    """Raised when a URL cannot be normalized into an HTTP(S) URL."""


def normalize_url(
    url: str,
    *,
    base_url: str | None = None,
    strip_tracking_params: bool = True,
    default_scheme: str = DEFAULT_SCHEME,
) -> str:
    """Normalize a URL for stable crawl/cache comparisons.

    Relative URLs require a ``base_url``. Absolute URLs without a scheme are
    treated as HTTPS by default because users commonly submit ``example.com``.
    """

    raw_url = url.strip()
    if not raw_url:
        raise UrlNormalizationError("URL is empty.")

    if raw_url.lower().startswith(BLOCKED_SCHEME_PREFIXES):
        raise UrlNormalizationError("URL uses a non-crawlable scheme.")

    if base_url is not None:
        raw_url = urljoin(base_url, raw_url)
    elif raw_url.startswith("//"):
        raw_url = f"{default_scheme}:{raw_url}"
    elif "://" not in raw_url:
        raw_url = f"{default_scheme}://{raw_url}"

    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UrlNormalizationError("Only HTTP and HTTPS URLs are crawlable.")

    hostname = parsed.hostname
    if not hostname:
        raise UrlNormalizationError("URL is missing a host.")

    hostname = hostname.lower()
    try:
        port = parsed.port
    except ValueError as exc:
        raise UrlNormalizationError("URL contains an invalid port.") from exc

    netloc = _normalized_netloc(scheme, hostname, port)
    path = _normalize_path(parsed.path)
    query = _normalize_query(parsed.query, strip_tracking_params=strip_tracking_params)

    return urlunsplit((scheme, netloc, path, query, ""))


def same_domain(
    url: str,
    base_url: str,
    *,
    allow_subdomains: bool = False,
) -> bool:
    """Return whether ``url`` belongs to the same host as ``base_url``.

    Leading ``www.`` is ignored. Other subdomains are excluded by default.
    """

    try:
        url_host = _host_for_comparison(normalize_url(url))
        base_host = _host_for_comparison(normalize_url(base_url))
    except UrlNormalizationError:
        return False

    if url_host == base_host:
        return True
    if allow_subdomains:
        return url_host.endswith(f".{base_host}")
    return False


def canonical_url_equal(left_url: str, right_url: str) -> bool:
    """Compare two URLs after applying crawler normalization."""

    try:
        return normalize_url(left_url) == normalize_url(right_url)
    except UrlNormalizationError:
        return False


def get_site_root(url: str) -> str:
    """Return the normalized site root for a URL."""

    normalized_url = normalize_url(url)
    parsed = urlsplit(normalized_url)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def path_depth(url: str) -> int:
    """Return the number of path segments in a normalized URL."""

    path = urlsplit(normalize_url(url)).path
    return len([segment for segment in path.split("/") if segment])


def _normalized_netloc(scheme: str, hostname: str, port: int | None) -> str:
    default_port = (scheme == "http" and port == 80) or (
        scheme == "https" and port == 443
    )
    if port is None or default_port:
        return hostname
    return f"{hostname}:{port}"


def _normalize_path(path: str) -> str:
    if not path:
        return "/"

    collapsed_path = re.sub(r"/{2,}", "/", path)
    decoded_path = unquote(collapsed_path)
    encoded_path = quote(decoded_path, safe="/:@-._~!$&'()*+,;=")
    if encoded_path != "/":
        encoded_path = encoded_path.rstrip("/")
    return encoded_path or "/"


def _normalize_query(query: str, *, strip_tracking_params: bool) -> str:
    if not query:
        return ""

    query_params = parse_qsl(query, keep_blank_values=True)
    if strip_tracking_params:
        query_params = [
            (key, value)
            for key, value in query_params
            if not _is_tracking_param(key)
        ]
    query_params.sort(key=lambda item: (item[0], item[1]))
    return urlencode(query_params, doseq=True)


def _is_tracking_param(param_name: str) -> bool:
    lowered_name = param_name.lower()
    return lowered_name.startswith("utm_") or lowered_name in TRACKING_PARAM_NAMES


def _host_for_comparison(url: str) -> str:
    hostname = urlsplit(url).hostname or ""
    lowered_hostname = hostname.lower()
    if lowered_hostname.startswith("www."):
        return lowered_hostname[4:]
    return lowered_hostname
