"""Safe synchronous HTML fetching with httpx."""

from __future__ import annotations

from time import perf_counter

import httpx

from app.config import Settings, get_settings
from app.models.crawl import FetchResult, FetchStatus

DEFAULT_USER_AGENT = (
    "WebsiteContentAuditor/0.1 "
    "(local content audit tool; respectful same-domain crawler)"
)


class HttpxHtmlFetcher:
    """Fetch HTML pages and return structured results.

    The class is intentionally small and synchronous. The optional Playwright
    fallback uses the same ``fetch`` contract.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        timeout_seconds: float | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.timeout_seconds = timeout_seconds or self.settings.request_timeout_seconds
        self.user_agent = user_agent
        self.client = client

    def fetch(self, url: str) -> FetchResult:
        """Fetch a URL and return a structured HTML-only result."""

        started_at = perf_counter()
        try:
            response = self._get(url)
        except httpx.TimeoutException as exc:
            return self._error_result(
                url,
                FetchStatus.TIMEOUT,
                f"Request timed out: {exc}",
                started_at,
            )
        except httpx.InvalidURL as exc:
            return self._error_result(
                url,
                FetchStatus.INVALID_URL,
                f"Invalid URL: {exc}",
                started_at,
            )
        except httpx.RequestError as exc:
            return self._error_result(
                url,
                FetchStatus.NETWORK_ERROR,
                f"Network error: {exc}",
                started_at,
            )

        content_type = _clean_content_type(response.headers.get("content-type"))
        final_url = str(response.url)
        elapsed_ms = _elapsed_ms(started_at)

        if response.status_code != 200:
            return FetchResult(
                url=url,
                final_url=final_url,
                status=FetchStatus.HTTP_ERROR,
                ok=False,
                status_code=response.status_code,
                content_type=content_type,
                html=None,
                error=f"Unexpected HTTP status {response.status_code}.",
                elapsed_ms=elapsed_ms,
            )

        html = response.text
        if not _is_html_response(content_type, html):
            return FetchResult(
                url=url,
                final_url=final_url,
                status=FetchStatus.NON_HTML,
                ok=False,
                status_code=response.status_code,
                content_type=content_type,
                html=None,
                error="Response content type is not HTML.",
                elapsed_ms=elapsed_ms,
            )

        return FetchResult(
            url=url,
            final_url=final_url,
            status=FetchStatus.SUCCESS,
            ok=True,
            status_code=response.status_code,
            content_type=content_type,
            html=html,
            error=None,
            elapsed_ms=elapsed_ms,
        )

    def _get(self, url: str) -> httpx.Response:
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": self.user_agent,
        }

        if self.client is not None:
            return self.client.get(
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )

        with httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=headers,
        ) as client:
            return client.get(url)

    @staticmethod
    def _error_result(
        url: str,
        status: FetchStatus,
        message: str,
        started_at: float,
    ) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=None,
            status=status,
            ok=False,
            error=message,
            elapsed_ms=_elapsed_ms(started_at),
        )


def _clean_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return content_type.split(";", maxsplit=1)[0].strip().lower()


def _is_html_response(content_type: str | None, body: str) -> bool:
    if content_type in {"text/html", "application/xhtml+xml"}:
        return True
    if content_type is None:
        stripped_body = body.lstrip().lower()
        return stripped_body.startswith("<!doctype html") or stripped_body.startswith(
            "<html"
        )
    return False


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)
