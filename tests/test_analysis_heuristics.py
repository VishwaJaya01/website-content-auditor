"""Tests for deterministic pre-LLM heuristic analysis."""

from app.analysis.chunker import chunk_page
from app.analysis.heuristics import analyze_page_heuristics
from app.models.crawl import ExtractedPage, PageSection


def _page(
    *,
    url: str = "https://example.com/",
    title: str = "Example",
    h1: str = "Example",
    sections: list[PageSection],
) -> ExtractedPage:
    return ExtractedPage(
        url=url,
        title=title,
        h1=h1,
        text_char_count=sum(len(section.text) for section in sections),
        sections=sections,
    )


def _section(
    section_id: str,
    heading_text: str,
    text: str,
    order: int = 0,
) -> PageSection:
    return PageSection(
        section_id=section_id,
        heading_path=["Example", heading_text],
        heading_level=2,
        heading_text=heading_text,
        text=text,
        order=order,
    )


def _signal_types(page: ExtractedPage) -> set[str]:
    return {signal.signal_type for signal in analyze_page_heuristics(page).signals}


def test_heuristics_emit_thin_content_signal():
    page = _page(
        sections=[
            _section("section-000", "Overview", "Short intro."),
        ]
    )

    signal_types = _signal_types(page)

    assert "thin_page" in signal_types
    assert "thin_section" in signal_types


def test_heuristics_emit_long_paragraph_signal():
    long_paragraph = (
        "This paragraph describes a service page with a lot of dense explanation "
        "but no meaningful break for readers who need to scan the content quickly. "
        * 10
    )
    page = _page(
        url="https://example.com/services",
        title="Services",
        h1="Services",
        sections=[_section("section-000", "Audit process", long_paragraph)],
    )

    signal_types = _signal_types(page)

    assert "long_paragraph" in signal_types


def test_heuristics_emit_missing_cta_for_commercial_homepage():
    text = (
        "Our product helps marketing teams review website pages, organize content "
        "feedback, and improve product messaging before launch. "
        "Teams use the service to evaluate page clarity, structure, and trust. "
        "The platform supports business websites with pricing, services, and "
        "product pages that need clearer messaging."
    )
    page = _page(
        url="https://example.com/",
        title="Example Product",
        h1="Website content audit platform",
        sections=[_section("section-000", "Product overview", text)],
    )

    signal_types = _signal_types(page)

    assert "missing_cta" in signal_types


def test_heuristics_emit_repeated_heading_and_phrase_signals():
    repeated_sentence = (
        "Every audit includes page-level findings for reviewers and stakeholders."
    )
    page = _page(
        sections=[
            _section("section-000", "Benefits", repeated_sentence, order=0),
            _section("section-001", "Benefits", repeated_sentence, order=1),
        ]
    )

    signal_types = _signal_types(page)

    assert "repeated_heading" in signal_types
    assert "repeated_phrase" in signal_types


def test_heuristics_emit_weak_structure_signal_for_low_section_count():
    page = _page(
        sections=[
            _section(
                "section-000",
                "Overview",
                "This page has enough words to avoid being completely thin, "
                "but it is still arranged as one broad section without support.",
            ),
        ]
    )

    signal_types = _signal_types(page)

    assert "weak_structure" in signal_types


def test_heuristics_emit_missing_trust_signal_for_commercial_page():
    text = (
        "Our services help businesses improve product pages and pricing pages "
        "with clearer copy, better structure, and stronger conversion messaging. "
        "The solution supports teams that need a practical website audit workflow "
        "for service launches, product updates, and marketing reviews."
    )
    page = _page(
        url="https://example.com/services",
        title="Services",
        h1="Services",
        sections=[_section("section-000", "Services", text)],
    )

    signal_types = _signal_types(page)

    assert "missing_trust_indicators" in signal_types


def test_heuristics_do_not_treat_documentation_homepage_as_commercial():
    text = (
        "Python documentation includes library references, language guides, "
        "tutorials, and setup instructions for developers using Python."
    )
    page = _page(
        url="https://docs.python.org/",
        title="3.14.4 Documentation",
        h1="Python Documentation",
        sections=[_section("section-000", "Documentation", text)],
    )

    signal_types = _signal_types(page)

    assert "missing_trust_indicators" not in signal_types


def test_heuristics_accept_precomputed_chunks_for_chunk_level_signals():
    very_long_word_block = " ".join(["analysis"] * 500)
    page = _page(
        sections=[_section("section-000", "Dense section", very_long_word_block)]
    )
    chunks = chunk_page(page, max_chars=120, target_chars=90)

    summary = analyze_page_heuristics(page, chunks=chunks)

    assert summary.page_url == page.url
    assert "oversized_chunk" not in summary.signal_counts
    assert summary.signal_counts
