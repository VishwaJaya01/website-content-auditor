"""Optional browser-backed HTML fetching for JavaScript-rendered pages."""

from __future__ import annotations

from importlib import import_module
from time import perf_counter

from app.config import Settings, get_settings
from app.models.crawl import FetchResult, FetchStatus

from .fetcher import (
    DEFAULT_USER_AGENT,
    _clean_content_type,
    _elapsed_ms,
    _is_html_response,
)


class PlaywrightHtmlFetcher:
    """Fetch rendered HTML with Playwright when the normal HTTP fetch is weak.

    Playwright is intentionally optional. The import happens inside ``fetch`` so
    the default local setup remains lightweight until browser fallback is used.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        timeout_seconds: float | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.settings = settings or get_settings()
        self.timeout_seconds = timeout_seconds or self.settings.request_timeout_seconds
        self.user_agent = user_agent

    def fetch(self, url: str) -> FetchResult:
        """Render a URL in headless Chromium and return the final HTML."""

        started_at = perf_counter()
        try:
            playwright_sync = import_module("playwright.sync_api")
        except ImportError:
            return self._error_result(
                url,
                FetchStatus.NETWORK_ERROR,
                (
                    "Playwright fallback is enabled but Playwright is not "
                    'installed. Install with: pip install -e ".[browser]" '
                    "and then run: playwright install chromium."
                ),
                started_at,
            )

        playwright_error = playwright_sync.Error
        playwright_timeout_error = playwright_sync.TimeoutError
        timeout_ms = int(self.timeout_seconds * 1000)
        try:
            with playwright_sync.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    page = browser.new_page(user_agent=self.user_agent)
                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    try:
                        page.wait_for_load_state(
                            "networkidle",
                            timeout=min(timeout_ms, 5000),
                        )
                    except playwright_timeout_error:
                        pass

                    html = page.content()
                    final_url = page.url
                    status_code = response.status if response is not None else None
                    content_type = (
                        _clean_content_type(response.headers.get("content-type"))
                        if response is not None
                        else None
                    )
                finally:
                    browser.close()
        except playwright_timeout_error as exc:
            return self._error_result(
                url,
                FetchStatus.TIMEOUT,
                f"Playwright render timed out: {exc}",
                started_at,
            )
        except playwright_error as exc:
            return self._error_result(
                url,
                FetchStatus.NETWORK_ERROR,
                f"Playwright render failed: {exc}",
                started_at,
            )

        elapsed_ms = _elapsed_ms(started_at)
        if status_code is not None and status_code >= 400:
            return FetchResult(
                url=url,
                final_url=final_url,
                status=FetchStatus.HTTP_ERROR,
                ok=False,
                status_code=status_code,
                content_type=content_type,
                html=None,
                error=f"Unexpected HTTP status {status_code}.",
                elapsed_ms=elapsed_ms,
            )

        if not _is_html_response(content_type, html):
            return FetchResult(
                url=url,
                final_url=final_url,
                status=FetchStatus.NON_HTML,
                ok=False,
                status_code=status_code,
                content_type=content_type,
                html=None,
                error="Rendered response content is not HTML.",
                elapsed_ms=elapsed_ms,
            )

        return FetchResult(
            url=url,
            final_url=final_url,
            status=FetchStatus.SUCCESS,
            ok=True,
            status_code=status_code,
            content_type=content_type or "text/html",
            html=html,
            error=None,
            elapsed_ms=elapsed_ms,
        )

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
