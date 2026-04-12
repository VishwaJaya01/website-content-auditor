"""Tests for crawler link filtering."""

from app.crawler.filters import (
    filter_link,
    is_non_html_asset_url,
)

BASE_URL = "https://example.com/"


def test_filter_link_skips_empty_fragment_and_blocked_schemes():
    empty_decision = filter_link("", base_url=BASE_URL, site_root_url=BASE_URL)
    mailto_decision = filter_link(
        "mailto:test@example.com",
        base_url=BASE_URL,
        site_root_url=BASE_URL,
    )

    assert empty_decision.reason == "empty_link"
    assert (
        filter_link("#team", base_url=BASE_URL, site_root_url=BASE_URL).reason
        == "fragment_only"
    )
    assert mailto_decision.reason == "blocked_scheme"


def test_filter_link_rejects_external_domains():
    decision = filter_link(
        "https://competitor.example/about",
        base_url=BASE_URL,
        site_root_url=BASE_URL,
    )

    assert not decision.allowed
    assert decision.reason == "external_domain"


def test_filter_link_rejects_non_html_assets():
    decision = filter_link(
        "/assets/logo.png",
        base_url=BASE_URL,
        site_root_url=BASE_URL,
    )

    assert not decision.allowed
    assert decision.reason == "non_html_asset"
    assert is_non_html_asset_url("https://example.com/brochure.pdf")


def test_filter_link_rejects_low_value_paths():
    decision = filter_link("/login", base_url=BASE_URL, site_root_url=BASE_URL)

    assert not decision.allowed
    assert decision.reason == "low_value_path"


def test_filter_link_cleans_fragment_and_tracking_params():
    decision = filter_link(
        "/about/?utm_source=social&ref=footer#team",
        base_url=BASE_URL,
        site_root_url=BASE_URL,
    )

    assert decision.allowed
    assert decision.normalized_url == "https://example.com/about?ref=footer"


def test_filter_link_rejects_seen_duplicates_after_normalization():
    seen_urls = {"https://example.com/about"}

    decision = filter_link(
        "/about/?utm_medium=email#top",
        base_url=BASE_URL,
        site_root_url=BASE_URL,
        seen_urls=seen_urls,
    )

    assert not decision.allowed
    assert decision.reason == "duplicate_url"
