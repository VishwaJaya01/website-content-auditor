"""Tests for safe HTML fetching without network access."""

import httpx

from app.crawler.fetcher import HttpxHtmlFetcher
from app.models.crawl import FetchStatus


def test_fetcher_returns_html_success_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body>Hello</body></html>",
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpxHtmlFetcher(timeout_seconds=1, client=client)
        result = fetcher.fetch("https://example.com/")

    assert result.ok
    assert result.status == FetchStatus.SUCCESS
    assert result.content_type == "text/html"
    assert result.html == "<html><body>Hello</body></html>"


def test_fetcher_rejects_non_html_content_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4",
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpxHtmlFetcher(timeout_seconds=1, client=client)
        result = fetcher.fetch("https://example.com/file.pdf")

    assert not result.ok
    assert result.status == FetchStatus.NON_HTML
    assert result.html is None


def test_fetcher_handles_non_200_status_with_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            headers={"content-type": "text/html"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetcher = HttpxHtmlFetcher(timeout_seconds=1, client=client)
        result = fetcher.fetch("https://example.com/missing")

    assert not result.ok
    assert result.status == FetchStatus.HTTP_ERROR
    assert result.status_code == 404
