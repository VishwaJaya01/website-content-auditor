"""Tests for section-aware content chunking."""

from app.analysis.chunker import chunk_page
from app.models.crawl import ExtractedPage, PageSection


def _page_with_sections(sections: list[PageSection]) -> ExtractedPage:
    return ExtractedPage(
        url="https://example.com/services",
        title="Services",
        h1="Content audit services",
        text_char_count=sum(len(section.text) for section in sections),
        sections=sections,
    )


def test_short_section_stays_one_chunk_with_metadata_preserved():
    page = _page_with_sections(
        [
            PageSection(
                section_id="section-000",
                heading_path=["Content audit services", "Overview"],
                heading_level=2,
                heading_text="Overview",
                text=(
                    "We audit service pages and turn unclear copy into "
                    "focused recommendations."
                ),
                order=0,
            )
        ]
    )

    chunks = chunk_page(page)

    assert len(chunks) == 1
    assert chunks[0].page_url == "https://example.com/services"
    assert chunks[0].page_title == "Services"
    assert chunks[0].page_h1 == "Content audit services"
    assert chunks[0].section_id == "section-000"
    assert chunks[0].section_path == ["Content audit services", "Overview"]
    assert chunks[0].section_heading == "Overview"
    assert chunks[0].chunk_order == 0
    assert chunks[0].token_estimate > 0


def test_long_section_splits_into_multiple_section_scoped_chunks():
    long_text = "\n\n".join(
        [
            (
                "Paragraph one explains the audit workflow for teams that need "
                "clearer content recommendations before publishing website updates."
            ),
            (
                "Paragraph two explains how reviewers can scan findings by page, "
                "section, priority, and evidence snippet without opening every page."
            ),
            (
                "Paragraph three explains why structured chunks are easier for a "
                "local language model to analyze reliably in later pipeline steps."
            ),
        ]
    )
    page = _page_with_sections(
        [
            PageSection(
                section_id="section-001",
                heading_path=["Content audit services", "Process"],
                heading_level=2,
                heading_text="Process",
                text=long_text,
                order=0,
            )
        ]
    )

    chunks = chunk_page(page, max_chars=150, target_chars=140)

    assert len(chunks) > 1
    assert {chunk.section_id for chunk in chunks} == {"section-001"}
    assert [chunk.chunk_order for chunk in chunks] == list(range(len(chunks)))
    assert all("split_long_section" in chunk.warnings for chunk in chunks)


def test_chunk_ids_are_deterministic_across_runs():
    page = _page_with_sections(
        [
            PageSection(
                section_id="section-abc",
                heading_path=["Services"],
                heading_level=1,
                heading_text="Services",
                text="Content audits help teams make website messaging clearer.",
                order=0,
            )
        ]
    )

    first = chunk_page(page)
    second = chunk_page(page)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
