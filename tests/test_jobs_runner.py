"""Tests for end-to-end pipeline runner behavior with fake dependencies."""

from app.analysis.embeddings import build_chunk_embedding
from app.jobs.manager import JobManager
from app.jobs.runner import AuditPipelineRunner
from app.models.analysis import (
    ChunkAnalysisResult,
    ContentChunk,
    ImprovementRecommendation,
    SignalSeverity,
)
from app.models.api import AnalyzeRequest
from app.models.crawl import CrawlResult, FetchResult, FetchStatus
from app.models.jobs import JobStatus
from app.storage.database import init_db

HTML_PAGE = """
<html>
  <head><title>Services</title></head>
  <body>
    <main>
      <h1>Website audit services</h1>
      <p>
        Our website audit service reviews page clarity, trust signals, pricing
        explanations, customer proof, and calls to action for teams improving
        their service pages before launch.
      </p>
    </main>
  </body>
</html>
"""

APP_SHELL_HTML = """
<html>
  <head><title>Client App</title></head>
  <body><main><div id="root"></div></main></body>
</html>
"""

RENDERED_HTML_PAGE = """
<html>
  <head><title>Rendered Services</title></head>
  <body>
    <main>
      <h1>Rendered website audit services</h1>
      <section>
        <h2>Content review process</h2>
        <p>
          Our rendered service page explains the audit process, proof points,
          customer reassurance, pricing next steps, and how teams request a
          content review after reading the page.
        </p>
      </section>
    </main>
  </body>
</html>
"""


def _request(
    url: str = "https://example.com",
    *,
    use_playwright_fallback: bool | None = None,
) -> AnalyzeRequest:
    return AnalyzeRequest(
        url=url,
        max_pages=2,
        max_depth=1,
        use_playwright_fallback=use_playwright_fallback,
    )


def _discovery_success(*args, **kwargs) -> CrawlResult:
    return CrawlResult(
        start_url="https://example.com",
        normalized_start_url="https://example.com/",
        fetch_results=[
            FetchResult(
                url="https://example.com/",
                final_url="https://example.com/",
                status=FetchStatus.SUCCESS,
                ok=True,
                status_code=200,
                content_type="text/html",
                html=HTML_PAGE,
            )
        ],
    )


def _discovery_partial(*args, **kwargs) -> CrawlResult:
    result = _discovery_success()
    result.fetch_results.append(
        FetchResult(
            url="https://example.com/missing",
            status=FetchStatus.HTTP_ERROR,
            ok=False,
            status_code=404,
            error="Unexpected HTTP status 404.",
        )
    )
    return result


def _discovery_no_content(*args, **kwargs) -> CrawlResult:
    return CrawlResult(
        start_url="https://example.com",
        normalized_start_url="https://example.com/",
        fetch_results=[],
    )


def _discovery_app_shell(*args, **kwargs) -> CrawlResult:
    return CrawlResult(
        start_url="https://example.com",
        normalized_start_url="https://example.com/",
        fetch_results=[
            FetchResult(
                url="https://example.com/",
                final_url="https://example.com/",
                status=FetchStatus.SUCCESS,
                ok=True,
                status_code=200,
                content_type="text/html",
                html=APP_SHELL_HTML,
            )
        ],
    )


class FakeEmbeddingProvider:
    def embed_chunks(self, chunks: list[ContentChunk]):
        return [build_chunk_embedding(chunk, [1.0, 0.0]) for chunk in chunks]


class FakeChunkAnalyzer:
    def __init__(self, *, warning: str | None = None) -> None:
        self.warning = warning

    def analyze_chunk(
        self,
        chunk: ContentChunk,
        *,
        heuristic_signals=None,
        similar_matches=None,
        duplicate_findings=None,
    ) -> ChunkAnalysisResult:
        if self.warning:
            return ChunkAnalysisResult(
                chunk_id=chunk.chunk_id,
                page_url=chunk.page_url,
                section_id=chunk.section_id,
                section_path=chunk.section_path,
                warnings=[self.warning],
            )
        return ChunkAnalysisResult(
            chunk_id=chunk.chunk_id,
            page_url=chunk.page_url,
            section_id=chunk.section_id,
            section_path=chunk.section_path,
            improvements=[
                ImprovementRecommendation(
                    category="clarity",
                    page_url=chunk.page_url,
                    section_id=chunk.section_id,
                    section_path=chunk.section_path,
                    issue="The section could explain the audit outcome more clearly.",
                    suggested_change="Add one sentence naming the deliverable.",
                    reason="A concrete deliverable makes the service easier to assess.",
                    severity=SignalSeverity.MEDIUM,
                    confidence=0.8,
                    evidence_snippet=chunk.chunk_text[:80],
                )
            ],
        )


class FakePlaywrightFetcher:
    def fetch(self, url: str) -> FetchResult:
        return FetchResult(
            url=url,
            final_url=url,
            status=FetchStatus.SUCCESS,
            ok=True,
            status_code=200,
            content_type="text/html",
            html=RENDERED_HTML_PAGE,
        )


def _runner(
    tmp_path,
    discovery_function,
    analyzer=None,
    request: AnalyzeRequest | None = None,
    playwright_fetcher=None,
) -> tuple[AuditPipelineRunner, str]:
    db_path = str(tmp_path / "auditor.db")
    init_db(db_path)
    manager = JobManager()
    manager.settings.sqlite_database_path = db_path
    manager.settings.reports_directory = str(tmp_path / "reports")
    manager.db_path = db_path
    job = manager.create_job(request or _request())
    runner = AuditPipelineRunner(
        settings=manager.settings,
        manager=manager,
        discovery_function=discovery_function,
        embedding_provider=FakeEmbeddingProvider(),
        chunk_analyzer=analyzer or FakeChunkAnalyzer(),
        playwright_fetcher=playwright_fetcher,
    )
    return runner, job.job_id


def test_runner_completes_and_persists_result(tmp_path):
    runner, job_id = _runner(tmp_path, _discovery_success)

    result = runner.run(job_id)
    job = runner.manager.get_job(job_id)
    cached_job = runner.manager.get_cached_job(_request())

    assert result is not None
    assert result.status == JobStatus.COMPLETED
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert cached_job is not None
    assert cached_job.job_id == job_id
    assert result.summary.pages_analyzed == 1
    assert result.html_report_path
    assert result.html_report_url == f"/reports/{job_id}"
    assert result.pages[0].improvement_recommendations


def test_runner_marks_partial_when_some_pages_fail(tmp_path):
    runner, job_id = _runner(tmp_path, _discovery_partial)

    result = runner.run(job_id)
    job = runner.manager.get_job(job_id)
    cached_job = runner.manager.get_cached_job(_request())

    assert result is not None
    assert result.status == JobStatus.PARTIAL
    assert job is not None
    assert job.status == JobStatus.PARTIAL
    assert result.failed_pages
    assert cached_job is not None
    assert cached_job.job_id == job_id


def test_runner_marks_failed_when_no_usable_content_exists(tmp_path):
    runner, job_id = _runner(tmp_path, _discovery_no_content)

    result = runner.run(job_id)
    job = runner.manager.get_job(job_id)

    assert result is None
    assert job is not None
    assert job.status == JobStatus.FAILED
    assert "No accessible pages" in (job.error_message or "")


def test_runner_uses_playwright_fallback_when_extraction_is_empty(tmp_path):
    runner, job_id = _runner(
        tmp_path,
        _discovery_app_shell,
        request=_request(use_playwright_fallback=True),
        playwright_fetcher=FakePlaywrightFetcher(),
    )

    result = runner.run(job_id)

    assert result is not None
    assert result.status == JobStatus.COMPLETED
    assert result.summary.pages_analyzed == 1
    assert result.pages[0].title == "Rendered Services"
    assert "Playwright fallback recovered" in " ".join(result.warnings)


def test_runner_marks_partial_when_llm_chunk_analysis_warns(tmp_path):
    runner, job_id = _runner(
        tmp_path,
        _discovery_success,
        analyzer=FakeChunkAnalyzer(warning="provider_error: Ollama unavailable"),
    )

    result = runner.run(job_id)

    assert result is not None
    assert result.status == JobStatus.PARTIAL
    assert "provider_error" in " ".join(result.warnings)
    assert runner.manager.get_cached_job(_request()) is None


def test_runner_does_not_mark_partial_for_output_quality_warnings_only(tmp_path):
    runner, job_id = _runner(
        tmp_path,
        _discovery_success,
        analyzer=FakeChunkAnalyzer(warning="dropped_missing_content_missing_required_text"),
    )

    result = runner.run(job_id)

    assert result is not None
    assert result.status == JobStatus.COMPLETED
    assert "dropped_missing_content" in " ".join(result.warnings)
