"""Visible text extraction and heading-aware section building."""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from app.models.crawl import CrawlWarning, ExtractedPage, FetchResult, PageSection
from app.utils.text import has_letters, normalize_whitespace

from .url_normalizer import UrlNormalizationError, normalize_url

REMOVABLE_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "template",
    "object",
    "embed",
}
HEADING_TAGS = {"h1", "h2", "h3", "h4"}
CONTENT_TAGS = {
    "p",
    "li",
    "blockquote",
    "figcaption",
    "summary",
    "td",
    "th",
}
CTA_TEXT_TAGS = {"button", "a"}
BOILERPLATE_TOKENS = {
    "ad",
    "ads",
    "advert",
    "advertisement",
    "banner",
    "cc-window",
    "consent",
    "cookie",
    "dialog",
    "gdpr",
    "modal",
    "newsletter-popup",
    "overlay",
    "popup",
    "privacy-banner",
}
HEADER_CHROME_TOKENS = {"site-header", "global-header", "masthead", "topbar"}
SIDEBAR_TOKENS = {"sidebar", "share", "social", "related-posts"}
GENERIC_NOISE_TEXT = {
    "accept",
    "accept all",
    "close",
    "home",
    "menu",
    "next",
    "ok",
    "previous",
    "read more",
    "skip to content",
}
MEANINGFUL_CTA_WORDS = {
    "book",
    "buy",
    "contact",
    "demo",
    "download",
    "get",
    "learn",
    "request",
    "schedule",
    "shop",
    "start",
    "subscribe",
    "try",
}
LOW_TEXT_THRESHOLD = 120


@dataclass
class _SectionDraft:
    heading_path: list[str]
    heading_level: int | None
    heading_text: str | None
    order: int
    source_selector: str | None
    blocks: list[str] = field(default_factory=list)


def extract_page(fetch_result: FetchResult) -> ExtractedPage:
    """Extract structured visible content from a successful HTML fetch result."""

    if not fetch_result.ok or not fetch_result.html:
        warning_code = fetch_result.status.value
        return ExtractedPage(
            url=fetch_result.url,
            final_url=fetch_result.final_url,
            status_code=fetch_result.status_code,
            content_type=fetch_result.content_type,
            warnings=[
                CrawlWarning(
                    code=warning_code,
                    message=fetch_result.error or "No HTML was available to extract.",
                    url=fetch_result.url,
                )
            ],
        )

    return extract_html(
        url=fetch_result.url,
        html=fetch_result.html,
        final_url=fetch_result.final_url,
        status_code=fetch_result.status_code,
        content_type=fetch_result.content_type,
    )


def extract_html(
    *,
    url: str,
    html: str,
    final_url: str | None = None,
    status_code: int | None = None,
    content_type: str | None = None,
) -> ExtractedPage:
    """Extract title, H1, warnings, and heading-aware sections from HTML."""

    base_url = final_url or url
    soup = BeautifulSoup(html, "html.parser")
    raw_body_text_count = len(_element_text(soup.body or soup))

    title = _extract_title(soup)
    canonical_url = _extract_canonical_url(soup, base_url)

    _remove_non_content_elements(soup)
    main_content = _select_main_content(soup)

    h1 = _first_meaningful_heading(soup, "h1")
    sections, had_headings = _build_sections(main_content, title=title)
    text_char_count = sum(len(section.text) for section in sections)
    warnings = _build_warnings(
        url=url,
        title=title,
        h1=h1,
        had_headings=had_headings,
        text_char_count=text_char_count,
        raw_body_text_count=raw_body_text_count,
    )

    return ExtractedPage(
        url=url,
        final_url=final_url,
        canonical_url=canonical_url,
        title=title,
        h1=h1,
        status_code=status_code,
        content_type=content_type,
        text_char_count=text_char_count,
        sections=sections,
        warnings=warnings,
    )


def _remove_non_content_elements(soup: BeautifulSoup) -> None:
    for tag_name in REMOVABLE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in list(soup.find_all(True)):
        if tag.name is None or tag.attrs is None:
            continue
        if _is_hidden(tag) or _is_boilerplate_container(tag):
            tag.decompose()
            continue
        if tag.name in {"nav", "footer"}:
            tag.decompose()
            continue
        if tag.name == "header" and _looks_like_header_chrome(tag):
            tag.decompose()
            continue
        if tag.name == "aside" and _looks_like_sidebar_noise(tag):
            tag.decompose()


def _select_main_content(soup: BeautifulSoup) -> Tag:
    semantic_candidates: list[Tag] = []
    for selector in ("main", "article", '[role="main"]'):
        semantic_candidates.extend(soup.select(selector))
    semantic_candidates = _dedupe_tags(semantic_candidates)
    if semantic_candidates:
        return max(semantic_candidates, key=_content_score)

    common_selectors = (
        "#content",
        "#main-content",
        "#primary",
        ".content",
        ".main-content",
        ".page-content",
        ".entry-content",
        ".post-content",
        ".site-content",
    )
    common_candidates: list[Tag] = []
    for selector in common_selectors:
        common_candidates.extend(soup.select(selector))
    common_candidates = [
        candidate
        for candidate in _dedupe_tags(common_candidates)
        if _content_score(candidate)
    ]
    if common_candidates:
        return max(common_candidates, key=_content_score)

    return soup.body or soup


def _build_sections(root: Tag, *, title: str | None) -> tuple[list[PageSection], bool]:
    drafts: list[_SectionDraft] = []
    heading_stack: dict[int, str] = {}
    current_section: _SectionDraft | None = None
    seen_fragments: set[str] = set()
    had_headings = False

    for tag in root.descendants:
        if not isinstance(tag, Tag):
            continue

        tag_name = tag.name.lower()
        if tag_name in HEADING_TAGS:
            heading_text = _meaningful_text(tag)
            if not _is_meaningful_heading(heading_text):
                continue
            heading_level = int(tag_name[1])
            heading_stack = {
                level: text
                for level, text in heading_stack.items()
                if level < heading_level
            }
            heading_stack[heading_level] = heading_text
            heading_path = [
                heading_stack[level]
                for level in sorted(heading_stack)
                if level <= heading_level
            ]
            current_section = _SectionDraft(
                heading_path=heading_path,
                heading_level=heading_level,
                heading_text=heading_text,
                order=len(drafts),
                source_selector=_source_selector(tag),
            )
            drafts.append(current_section)
            had_headings = True
            continue

        if not _should_extract_text_from_tag(tag):
            continue

        text = _meaningful_text(tag)
        if not _is_meaningful_content_text(text, tag):
            continue
        if _is_repeated_low_value_fragment(text, seen_fragments):
            continue

        if current_section is None:
            current_section = _SectionDraft(
                heading_path=[title or "Page Content"],
                heading_level=None,
                heading_text=title or "Page Content",
                order=len(drafts),
                source_selector=None,
            )
            drafts.append(current_section)

        current_section.blocks.append(text)

    sections = _finalize_sections(drafts)
    if sections:
        return sections, had_headings

    fallback_text = _meaningful_text(root)
    if _is_meaningful_content_text(fallback_text, root):
        fallback_section = PageSection(
            section_id="section-000",
            heading_path=[title or "Page Content"],
            heading_level=None,
            heading_text=title or "Page Content",
            text=fallback_text,
            order=0,
            source_selector=None,
        )
        return [fallback_section], had_headings

    return [], had_headings


def _finalize_sections(drafts: list[_SectionDraft]) -> list[PageSection]:
    sections: list[PageSection] = []
    for draft in drafts:
        text = normalize_whitespace(" ".join(draft.blocks))
        if not text:
            continue
        order = len(sections)
        sections.append(
            PageSection(
                section_id=f"section-{order:03d}",
                heading_path=draft.heading_path,
                heading_level=draft.heading_level,
                heading_text=draft.heading_text,
                text=text,
                order=order,
                source_selector=draft.source_selector,
            )
        )
    return sections


def _build_warnings(
    *,
    url: str,
    title: str | None,
    h1: str | None,
    had_headings: bool,
    text_char_count: int,
    raw_body_text_count: int,
) -> list[CrawlWarning]:
    warnings: list[CrawlWarning] = []

    if title is None:
        warnings.append(
            CrawlWarning(
                code="missing_title",
                message="Page title is missing.",
                url=url,
            )
        )
    if h1 is None:
        warnings.append(
            CrawlWarning(
                code="missing_h1",
                message="Page has no meaningful H1.",
                url=url,
            )
        )
    if not had_headings:
        warnings.append(
            CrawlWarning(
                code="no_meaningful_headings",
                message="Page has no meaningful H1-H4 headings.",
                url=url,
            )
        )
    if text_char_count < LOW_TEXT_THRESHOLD:
        warnings.append(
            CrawlWarning(
                code="low_text",
                message="Extracted visible text is very limited.",
                url=url,
            )
        )
    if raw_body_text_count >= 300 and text_char_count < 100:
        warnings.append(
            CrawlWarning(
                code="mostly_boilerplate",
                message="Most body text appears to be boilerplate or non-content.",
                url=url,
            )
        )

    return warnings


def _extract_title(soup: BeautifulSoup) -> str | None:
    if soup.title is None:
        return None
    title = normalize_whitespace(soup.title.get_text(" ", strip=True))
    return title if _is_meaningful_text(title, min_words=1, min_chars=2) else None


def _extract_canonical_url(soup: BeautifulSoup, base_url: str) -> str | None:
    canonical_tag = soup.find(
        "link",
        rel=lambda value: _rel_contains(value, "canonical"),
    )
    if not isinstance(canonical_tag, Tag):
        return None
    href = canonical_tag.get("href")
    if not isinstance(href, str) or not href.strip():
        return None
    try:
        return normalize_url(href, base_url=base_url)
    except UrlNormalizationError:
        return None


def _first_meaningful_heading(soup: BeautifulSoup, heading_name: str) -> str | None:
    for heading in soup.find_all(heading_name):
        text = _meaningful_text(heading)
        if _is_meaningful_heading(text):
            return text
    return None


def _should_extract_text_from_tag(tag: Tag) -> bool:
    tag_name = tag.name.lower()
    if tag_name in CONTENT_TAGS:
        return not _has_content_tag_ancestor(tag)
    if tag_name in CTA_TEXT_TAGS:
        return _looks_like_meaningful_cta(tag)
    return False


def _is_meaningful_content_text(text: str, tag: Tag) -> bool:
    if tag.name.lower() in CTA_TEXT_TAGS:
        return _is_meaningful_text(
            text,
            min_words=2,
            min_chars=4,
        ) and _looks_like_cta_text(text)
    if not _is_meaningful_text(text, min_words=2, min_chars=12):
        return False
    lowered_text = text.lower()
    if lowered_text in GENERIC_NOISE_TEXT:
        return False
    return True


def _is_meaningful_heading(text: str) -> bool:
    return _is_meaningful_text(text, min_words=1, min_chars=3)


def _is_meaningful_text(text: str, *, min_words: int, min_chars: int) -> bool:
    if len(text) < min_chars:
        return False
    if not has_letters(text):
        return False
    words = [word for word in text.split(" ") if word]
    return len(words) >= min_words


def _is_repeated_low_value_fragment(text: str, seen_fragments: set[str]) -> bool:
    key = normalize_whitespace(text).casefold()
    is_short_fragment = len(text) < 80 and len(text.split()) <= 6
    if is_short_fragment and key in seen_fragments:
        return True
    seen_fragments.add(key)
    return False


def _meaningful_text(tag: Tag) -> str:
    return normalize_whitespace(tag.get_text(" ", strip=True))


def _element_text(tag: Tag | BeautifulSoup) -> str:
    return normalize_whitespace(tag.get_text(" ", strip=True))


def _content_score(tag: Tag) -> int:
    text = _element_text(tag)
    link_text = " ".join(
        anchor.get_text(" ", strip=True) for anchor in tag.find_all("a")
    )
    heading_count = len(tag.find_all(list(HEADING_TAGS)))
    paragraph_count = len(tag.find_all(["p", "li", "blockquote"]))
    return len(text) + heading_count * 150 + paragraph_count * 20 - len(link_text)


def _dedupe_tags(tags: list[Tag]) -> list[Tag]:
    deduped: list[Tag] = []
    seen_ids: set[int] = set()
    for tag in tags:
        tag_id = id(tag)
        if tag_id in seen_ids:
            continue
        seen_ids.add(tag_id)
        deduped.append(tag)
    return deduped


def _is_hidden(tag: Tag) -> bool:
    if tag.has_attr("hidden"):
        return True
    if str(tag.get("aria-hidden", "")).lower() == "true":
        return True
    if tag.name == "input" and str(tag.get("type", "")).lower() == "hidden":
        return True
    style = str(tag.get("style", "")).replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def _is_boilerplate_container(tag: Tag) -> bool:
    role = str(tag.get("role", "")).lower()
    if role in {"dialog", "alertdialog"}:
        return True
    tokens = _attribute_tokens(tag)
    return bool(tokens.intersection(BOILERPLATE_TOKENS))


def _looks_like_header_chrome(tag: Tag) -> bool:
    tokens = _attribute_tokens(tag)
    has_header_token = bool(tokens.intersection(HEADER_CHROME_TOKENS))
    has_navigation = tag.find("nav") is not None
    has_primary_heading = tag.find(["h1", "h2"]) is not None
    return (has_header_token or has_navigation) and not has_primary_heading


def _looks_like_sidebar_noise(tag: Tag) -> bool:
    return bool(_attribute_tokens(tag).intersection(SIDEBAR_TOKENS))


def _attribute_tokens(tag: Tag) -> set[str]:
    values: list[str] = []
    for attribute_name in ("id", "class", "role", "aria-label"):
        attribute_value = tag.get(attribute_name)
        if isinstance(attribute_value, list):
            values.extend(str(item) for item in attribute_value)
        elif attribute_value is not None:
            values.append(str(attribute_value))

    tokens: set[str] = set()
    for value in values:
        normalized_value = normalize_whitespace(value).lower()
        tokens.add(normalized_value)
        tokens.update(
            token
            for token in normalized_value.replace("_", "-").split("-")
            if token
        )
    return tokens


def _has_content_tag_ancestor(tag: Tag) -> bool:
    for parent in tag.parents:
        if not isinstance(parent, Tag):
            continue
        if parent.name.lower() in CONTENT_TAGS:
            return True
    return False


def _looks_like_meaningful_cta(tag: Tag) -> bool:
    if tag.name.lower() == "button":
        return True
    if str(tag.get("role", "")).lower() == "button":
        return True
    tokens = _attribute_tokens(tag)
    return bool(tokens.intersection({"button", "btn", "cta", "action"}))


def _looks_like_cta_text(text: str) -> bool:
    lowered_words = {word.strip(".,!?:;").lower() for word in text.split()}
    if not lowered_words.intersection(MEANINGFUL_CTA_WORDS):
        return False
    return len(text.split()) <= 8


def _rel_contains(value: object, expected: str) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return expected in {str(item).lower() for item in value}
    return expected in str(value).lower().split()


def _source_selector(tag: Tag) -> str:
    if tag.get("id"):
        return f"{tag.name}#{tag.get('id')}"
    classes = tag.get("class")
    if isinstance(classes, list) and classes:
        return f"{tag.name}.{'.'.join(str(item) for item in classes[:2])}"
    return tag.name
