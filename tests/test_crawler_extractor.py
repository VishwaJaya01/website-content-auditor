"""Tests for visible text extraction and heading-aware sections."""

from app.crawler.extractor import extract_html, extract_page
from app.models.crawl import FetchResult, FetchStatus


def test_extract_html_builds_heading_aware_sections_from_main_content():
    html = """
    <html>
      <head>
        <title>Acme Audits</title>
        <link rel="canonical" href="/home/" />
      </head>
      <body>
        <main>
          <h1>Audit your website</h1>
          <p>Turn scattered website copy into clear recommendations for each page.</p>
          <h2>Features</h2>
          <p>Review clarity, trust signals, calls to action, and page structure.</p>
          <ul>
            <li>Find unclear text before customers leave the page.</li>
            <li>Group recommendations by page and section.</li>
          </ul>
        </main>
      </body>
    </html>
    """

    page = extract_html(url="https://example.com", html=html)

    assert page.title == "Acme Audits"
    assert page.h1 == "Audit your website"
    assert page.canonical_url == "https://example.com/home"
    assert len(page.sections) == 2
    assert page.sections[0].heading_path == ["Audit your website"]
    assert page.sections[0].heading_level == 1
    assert "clear recommendations" in page.sections[0].text
    assert page.sections[1].heading_path == ["Audit your website", "Features"]
    assert "Find unclear text" in page.sections[1].text


def test_extract_html_removes_nav_footer_cookie_modal_and_hidden_noise():
    html = """
    <html>
      <head><title>Enterprise Audits</title></head>
      <body>
        <header class="site-header">
          <nav><a href="/">Home</a><a href="/pricing">Pricing</a></nav>
        </header>
        <div class="cookie-banner">Accept cookies to continue</div>
        <div role="dialog">Subscribe to our newsletter popup</div>
        <p hidden>This hidden paragraph should not appear.</p>
        <main>
          <h1>Enterprise content audits</h1>
          <p>
            See which website pages need clearer proof, stronger messaging,
            and better calls to action.
          </p>
        </main>
        <footer>Copyright 2026 Example Inc. Privacy Terms</footer>
      </body>
    </html>
    """

    page = extract_html(url="https://example.com", html=html)
    extracted_text = " ".join(section.text for section in page.sections)

    assert "clearer proof" in extracted_text
    assert "Home" not in extracted_text
    assert "Pricing" not in extracted_text
    assert "Accept cookies" not in extracted_text
    assert "newsletter popup" not in extracted_text
    assert "hidden paragraph" not in extracted_text
    assert "Copyright" not in extracted_text


def test_extract_html_falls_back_when_page_has_no_headings():
    html = """
    <html>
      <head><title>About Acme</title></head>
      <body>
        <main>
          <p>Acme helps teams understand which website pages need stronger content.</p>
          <p>The audit workflow keeps recommendations organized by page for review.</p>
        </main>
      </body>
    </html>
    """

    page = extract_html(url="https://example.com/about", html=html)
    warning_codes = {warning.code for warning in page.warnings}

    assert len(page.sections) == 1
    assert page.sections[0].heading_text == "About Acme"
    assert "stronger content" in page.sections[0].text
    assert "no_meaningful_headings" in warning_codes
    assert "missing_h1" in warning_codes


def test_extract_html_keeps_meaningful_lists_tables_and_ctas():
    html = """
    <html>
      <head><title>Pricing</title></head>
      <body>
        <main>
          <h1>Simple pricing for content teams</h1>
          <table>
            <tr>
              <th>Starter</th>
              <td>Best for small teams auditing a few pages each month.</td>
            </tr>
          </table>
          <ul>
            <li>Includes page-level recommendations and exportable summaries.</li>
          </ul>
          <a class="btn" href="/demo">Book a demo</a>
          <button>Get started</button>
          <button>OK</button>
        </main>
      </body>
    </html>
    """

    page = extract_html(url="https://example.com/pricing", html=html)
    extracted_text = page.sections[0].text

    assert "Best for small teams" in extracted_text
    assert "page-level recommendations" in extracted_text
    assert "Book a demo" in extracted_text
    assert "Get started" in extracted_text
    assert " OK " not in f" {extracted_text} "


def test_extract_html_warns_for_very_low_text_pages():
    html = """
    <html>
      <head><title>Short Page</title></head>
      <body><main><h1>Hi</h1><p>Welcome.</p></main></body>
    </html>
    """

    page = extract_html(url="https://example.com/short", html=html)
    warning_codes = {warning.code for warning in page.warnings}

    assert page.text_char_count < 120
    assert "low_text" in warning_codes
    assert "no_meaningful_headings" in warning_codes


def test_extract_html_normalizes_whitespace():
    html = """
    <html>
      <head><title>Whitespace</title></head>
      <body>
        <main>
          <h1>Clean copy</h1>
          <p>
            This    paragraph
            has     inconsistent
            spacing.
          </p>
        </main>
      </body>
    </html>
    """

    page = extract_html(url="https://example.com/clean", html=html)

    assert page.sections[0].text == "This paragraph has inconsistent spacing."


def test_extract_page_returns_structured_warning_for_failed_fetch_result():
    fetch_result = FetchResult(
        url="https://example.com",
        status=FetchStatus.HTTP_ERROR,
        ok=False,
        status_code=500,
        error="Unexpected HTTP status 500.",
    )

    page = extract_page(fetch_result)

    assert page.sections == []
    assert page.status_code == 500
    assert page.warnings[0].code == "http_error"
