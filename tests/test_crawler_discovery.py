"""Tests for same-domain discovery and prioritization."""

from app.crawler.discovery import discover_site, score_url_priority
from app.models.crawl import FetchResult, FetchStatus


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.fetched_urls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.fetched_urls.append(url)
        html = self.pages.get(url, "<html><body></body></html>")
        return FetchResult(
            url=url,
            final_url=url,
            status=FetchStatus.SUCCESS,
            ok=True,
            status_code=200,
            content_type="text/html",
            html=html,
        )


def test_score_url_priority_boosts_important_pages_over_blog_posts():
    root = "https://example.com/"
    pricing_score, pricing_reason = score_url_priority(
        "https://example.com/pricing",
        root,
    )
    blog_score, blog_reason = score_url_priority("https://example.com/blog/post", root)

    assert pricing_score > blog_score
    assert pricing_reason == "important_path:pricing"
    assert blog_reason == "important_path:blog"


def test_discover_site_keeps_homepage_first_and_prioritizes_content_pages():
    pages = {
        "https://example.com/": """
            <html><body>
                <a href="/blog/launch?utm_source=email">Launch</a>
                <a href="/login">Login</a>
                <a href="/assets/logo.png">Logo</a>
                <a href="https://external.example/about">External</a>
                <a href="/pricing">Pricing</a>
                <a href="/about#team">About</a>
            </body></html>
        """,
    }
    fetcher = FakeFetcher(pages)

    result = discover_site(
        "https://example.com",
        max_pages=4,
        max_depth=1,
        fetcher=fetcher,
    )

    discovered = [item.url for item in result.discovered_urls]

    assert discovered[0] == "https://example.com/"
    assert "https://example.com/pricing" in discovered
    assert "https://example.com/about" in discovered
    assert "https://example.com/blog/launch" in discovered
    assert "https://example.com/login" not in discovered
    assert "https://example.com/assets/logo.png" not in discovered
    assert discovered.index("https://example.com/pricing") < discovered.index(
        "https://example.com/blog/launch"
    )


def test_discover_site_respects_max_depth():
    pages = {
        "https://example.com/": """
            <html><body><a href="/about">About</a></body></html>
        """,
        "https://example.com/about": """
            <html><body><a href="/contact">Contact</a></body></html>
        """,
    }
    fetcher = FakeFetcher(pages)

    result = discover_site(
        "https://example.com",
        max_pages=10,
        max_depth=1,
        fetcher=fetcher,
    )

    discovered = [item.url for item in result.discovered_urls]

    assert "https://example.com/about" in discovered
    assert "https://example.com/contact" not in discovered

