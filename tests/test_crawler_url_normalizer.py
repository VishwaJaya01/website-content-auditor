"""Tests for crawler URL normalization helpers."""

from app.crawler.url_normalizer import (
    canonical_url_equal,
    get_site_root,
    normalize_url,
    same_domain,
)


def test_normalize_url_adds_scheme_and_removes_tracking_and_fragment():
    normalized = normalize_url(
        " Example.COM/foo/?utm_source=newsletter&fbclid=abc&b=2#section "
    )

    assert normalized == "https://example.com/foo?b=2"


def test_normalize_url_preserves_root_slash_and_removes_non_root_trailing_slash():
    assert normalize_url("HTTP://WWW.Example.COM/") == "http://www.example.com/"
    assert normalize_url("https://example.com/about/") == "https://example.com/about"


def test_normalize_url_resolves_relative_links_against_base_url():
    normalized = normalize_url("../pricing/#plans", base_url="https://example.com/docs/")

    assert normalized == "https://example.com/pricing"


def test_same_domain_ignores_www_but_rejects_other_domains():
    assert same_domain("https://www.example.com/about", "https://example.com/")
    assert not same_domain("https://other.example.com/about", "https://example.com/")
    assert not same_domain("https://example.org/about", "https://example.com/")


def test_canonical_url_equal_uses_normalization():
    assert canonical_url_equal(
        "https://example.com/about/?utm_campaign=spring#team",
        "https://EXAMPLE.com/about",
    )


def test_get_site_root_returns_normalized_homepage():
    assert get_site_root("https://Example.com/about/team") == "https://example.com/"

