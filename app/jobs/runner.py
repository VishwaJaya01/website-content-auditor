"""End-to-end audit pipeline runner for one job."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from app.analysis.aggregator import aggregate_audit_result
from app.analysis.analyzer import ChunkAnalyzer
from app.analysis.chunker import chunk_page
from app.analysis.duplicate_detector import detect_cross_page_duplicates
from app.analysis.embeddings import (
    SentenceTransformerEmbeddingProvider,
    retrieve_similar_chunks,
)
from app.analysis.heuristics import analyze_page_heuristics
from app.config import Settings, get_settings
from app.crawler.discovery import discover_site
from app.crawler.extractor import extract_page
from app.crawler.playwright_fetcher import PlaywrightHtmlFetcher
from app.jobs.manager import JobManager
from app.models.analysis import (
    ChunkAnalysisResult,
    ChunkEmbedding,
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
)
from app.models.crawl import CrawlResult, ExtractedPage, FetchResult
from app.models.jobs import JobStatus
from app.models.results import AuditResultResponse, FailedPageRecord
from app.providers.ollama import OllamaProvider
from app.reports.html_report import write_html_report
from app.storage import repositories


class EmbeddingProvider(Protocol):
    """Small protocol for embedding providers used by the runner."""

    def embed_chunks(self, chunks: list[ContentChunk]) -> list[ChunkEmbedding]:
        """Embed analysis chunks."""


class ChunkAnalysisProvider(Protocol):
    """Small protocol for chunk-level analyzers used by the runner."""

    def analyze_chunk(
        self,
        chunk: ContentChunk,
        *,
        heuristic_signals: list[HeuristicSignal] | None = None,
        similar_matches: object | None = None,
        duplicate_findings: list[DuplicateContentFinding] | None = None,
    ) -> ChunkAnalysisResult:
        """Analyze one chunk."""


class HtmlFetchProvider(Protocol):
    """Small protocol for optional browser-backed fetchers."""

    def fetch(self, url: str) -> FetchResult:
        """Fetch one URL and return a structured result."""


DiscoveryFunction = Callable[..., CrawlResult]


class AuditPipelineRunner:
    """Coordinate crawling, extraction, analysis, aggregation, and persistence."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        manager: JobManager | None = None,
        discovery_function: DiscoveryFunction = discover_site,
        embedding_provider: EmbeddingProvider | None = None,
        chunk_analyzer: ChunkAnalysisProvider | None = None,
        playwright_fetcher: HtmlFetchProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.manager = manager or JobManager(self.settings)
        self.discovery_function = discovery_function
        self.embedding_provider = embedding_provider
        self.chunk_analyzer = chunk_analyzer
        self.playwright_fetcher = playwright_fetcher

    def run(self, job_id: str) -> AuditResultResponse | None:
        """Execute the complete audit pipeline for an existing job."""

        job = self.manager.get_job(job_id)
        if job is None:
            return None

        self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.05)
        request_config = self.manager.get_job_request_config(job_id)
        warnings: list[str] = []
        failed_pages: list[FailedPageRecord] = []

        try:
            crawl_result = self._discover(job.normalized_url, request_config)
            warnings.extend(warning.message for warning in crawl_result.warnings)
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.2)

            pages, extraction_failures, extraction_warnings = self._extract_pages(
                crawl_result,
                request_config,
            )
            failed_pages.extend(extraction_failures)
            warnings.extend(extraction_warnings)
            if not pages:
                self.manager.mark_failed(
                    job_id,
                    "No accessible pages with extractable HTML content were found.",
                )
                return None
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.35)

            chunks = self._chunk_pages(pages)
            if not chunks:
                self.manager.mark_failed(
                    job_id,
                    "No meaningful extracted text was available for analysis.",
                )
                return None
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.45)

            heuristic_signals = self._analyze_heuristics(pages, chunks)
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.55)

            embeddings, embedding_warnings = self._embed_chunks(chunks)
            warnings.extend(embedding_warnings)
            duplicate_findings = (
                detect_cross_page_duplicates(chunks, embeddings)
                if embeddings
                else []
            )
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.68)

            chunk_results = self._analyze_chunks_with_llm(
                chunks,
                heuristic_signals=heuristic_signals,
                duplicate_findings=duplicate_findings,
                embeddings=embeddings,
            )
            llm_warnings = [
                warning
                for result in chunk_results
                for warning in result.warnings
            ]
            critical_llm_warnings = [
                warning
                for warning in llm_warnings
                if _is_critical_llm_warning(warning)
            ]
            warnings.extend(llm_warnings)
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.9)

            final_status = (
                JobStatus.PARTIAL
                if failed_pages or embedding_warnings or critical_llm_warnings
                else JobStatus.COMPLETED
            )
            result = aggregate_audit_result(
                job_id=job_id,
                status=final_status,
                input_url=job.input_url,
                normalized_url=job.normalized_url,
                pages=pages,
                chunks=chunks,
                heuristic_signals=heuristic_signals,
                duplicate_findings=duplicate_findings,
                chunk_results=chunk_results,
                failed_pages=failed_pages,
                warnings=warnings,
            )
            self._maybe_write_html_report(result, request_config)
            repositories.save_audit_result(
                self.settings.sqlite_database_path,
                job_id=job_id,
                result=result.model_dump(mode="json"),
            )

            if final_status == JobStatus.COMPLETED:
                completed_job = self.manager.mark_completed(job_id)
                if completed_job is not None:
                    self.manager.save_cache_entry(completed_job)
            else:
                partial_job = self.manager.mark_partial(
                    job_id,
                    "Audit completed with partial results.",
                )
                if partial_job is not None and not critical_llm_warnings:
                    self.manager.save_cache_entry(partial_job)
            return result
        except Exception as exc:
            self.manager.mark_failed(job_id, f"Pipeline failed: {exc}")
            return None

    def _discover(
        self,
        normalized_url: str,
        request_config: dict[str, Any],
    ) -> CrawlResult:
        max_pages = int(
            request_config.get("max_pages") or self.settings.default_max_pages
        )
        max_depth = int(
            request_config.get("max_depth") or self.settings.default_max_depth
        )
        return self.discovery_function(
            normalized_url,
            max_pages=max_pages,
            max_depth=max_depth,
            settings=self.settings,
        )

    def _extract_pages(
        self,
        crawl_result: CrawlResult,
        request_config: dict[str, Any],
    ) -> tuple[list[ExtractedPage], list[FailedPageRecord], list[str]]:
        pages: list[ExtractedPage] = []
        failed_pages: list[FailedPageRecord] = []
        warnings: list[str] = []
        fallback_enabled = self._playwright_fallback_enabled(request_config)

        for fetch_result in crawl_result.fetch_results:
            active_fetch = fetch_result
            used_playwright = False
            if not active_fetch.ok and fallback_enabled:
                fallback_fetch, fallback_warning = self._fetch_with_playwright(
                    active_fetch.url
                )
                if fallback_warning:
                    warnings.append(fallback_warning)
                if fallback_fetch is not None and fallback_fetch.ok:
                    active_fetch = fallback_fetch
                    used_playwright = True

            page, failure = self._extract_fetch_result(active_fetch)
            if page is None:
                if fallback_enabled and not used_playwright:
                    fallback_fetch, fallback_warning = self._fetch_with_playwright(
                        active_fetch.final_url or active_fetch.url
                    )
                    if fallback_warning:
                        warnings.append(fallback_warning)
                    if fallback_fetch is not None and fallback_fetch.ok:
                        fallback_page, fallback_failure = self._extract_fetch_result(
                            fallback_fetch
                        )
                        if fallback_page is not None:
                            warnings.append(
                                "Playwright fallback recovered extractable content "
                                f"for {active_fetch.url}."
                            )
                            pages.append(fallback_page)
                            continue
                        if fallback_failure is not None:
                            failure = fallback_failure
                if failure is not None:
                    failed_pages.append(failure)
                continue

            if (
                fallback_enabled
                and not used_playwright
                and self._is_weak_extraction(page)
            ):
                fallback_fetch, fallback_warning = self._fetch_with_playwright(
                    active_fetch.final_url or active_fetch.url
                )
                if fallback_warning:
                    warnings.append(fallback_warning)
                if fallback_fetch is not None and fallback_fetch.ok:
                    fallback_page, fallback_failure = self._extract_fetch_result(
                        fallback_fetch
                    )
                    if fallback_page is not None and self._page_quality_score(
                        fallback_page
                    ) > self._page_quality_score(page):
                        warnings.append(
                            "Playwright fallback improved extraction for "
                            f"{page.url}."
                        )
                        pages.append(fallback_page)
                        continue
                    if fallback_failure is not None and page.text_char_count <= 0:
                        failed_pages.append(fallback_failure)
                        continue

            pages.append(page)

        return pages, failed_pages, warnings

    @staticmethod
    def _extract_fetch_result(
        fetch_result: FetchResult,
    ) -> tuple[ExtractedPage | None, FailedPageRecord | None]:
        if not fetch_result.ok:
            return None, FailedPageRecord(
                url=fetch_result.url,
                reason=fetch_result.error or fetch_result.status.value,
                stage="fetch",
            )

        try:
            page = extract_page(fetch_result)
        except Exception as exc:
            return None, FailedPageRecord(
                url=fetch_result.url,
                reason=f"Extraction failed: {exc}",
                stage="extraction",
            )

        if page.text_char_count <= 0 or not page.sections:
            return None, FailedPageRecord(
                url=page.url,
                reason="No meaningful visible text was extracted.",
                stage="extraction",
            )
        return page, None

    def _fetch_with_playwright(
        self,
        url: str,
    ) -> tuple[FetchResult | None, str | None]:
        fetcher = self.playwright_fetcher or PlaywrightHtmlFetcher(
            settings=self.settings
        )
        try:
            fetch_result = fetcher.fetch(url)
        except Exception as exc:
            return None, f"Playwright fallback failed for {url}: {exc}"

        if fetch_result.ok:
            return fetch_result, None
        return (
            fetch_result,
            (
                "Playwright fallback could not fetch "
                f"{url}: {fetch_result.error or fetch_result.status.value}"
            ),
        )

    def _playwright_fallback_enabled(self, request_config: dict[str, Any]) -> bool:
        return bool(
            request_config.get("use_playwright_fallback")
            or self.settings.enable_playwright_fallback
        )

    @staticmethod
    def _is_weak_extraction(page: ExtractedPage) -> bool:
        if not page.sections:
            return True
        if page.text_char_count < 300:
            return True
        return len(page.sections) <= 1 and page.text_char_count < 600

    @staticmethod
    def _page_quality_score(page: ExtractedPage) -> int:
        return page.text_char_count + (len(page.sections) * 120)

    @staticmethod
    def _chunk_pages(pages: list[ExtractedPage]) -> list[ContentChunk]:
        return [chunk for page in pages for chunk in chunk_page(page)]

    @staticmethod
    def _analyze_heuristics(
        pages: list[ExtractedPage],
        chunks: list[ContentChunk],
    ) -> list[HeuristicSignal]:
        chunks_by_page: dict[str, list[ContentChunk]] = {}
        for chunk in chunks:
            chunks_by_page.setdefault(chunk.page_url, []).append(chunk)

        signals: list[HeuristicSignal] = []
        for page in pages:
            summary = analyze_page_heuristics(
                page,
                chunks=chunks_by_page.get(page.url, []),
            )
            signals.extend(summary.signals)
        return signals

    def _embed_chunks(
        self,
        chunks: list[ContentChunk],
    ) -> tuple[list[ChunkEmbedding], list[str]]:
        provider = self.embedding_provider or SentenceTransformerEmbeddingProvider(
            settings=self.settings
        )
        try:
            return provider.embed_chunks(chunks), []
        except Exception as exc:
            return [], [f"Embedding generation failed: {exc}"]

    def _analyze_chunks_with_llm(
        self,
        chunks: list[ContentChunk],
        *,
        heuristic_signals: list[HeuristicSignal],
        duplicate_findings: list[DuplicateContentFinding],
        embeddings: list[ChunkEmbedding],
    ) -> list[ChunkAnalysisResult]:
        analyzer = self.chunk_analyzer or ChunkAnalyzer(
            OllamaProvider(settings=self.settings)
        )
        results: list[ChunkAnalysisResult] = []
        for chunk in chunks:
            similar_matches = (
                retrieve_similar_chunks(
                    chunk,
                    chunks,
                    embeddings,
                    top_k=3,
                    min_similarity=0.72,
                    cross_page_only=True,
                )
                if embeddings
                else []
            )
            relevant_duplicates = [
                finding
                for finding in duplicate_findings
                if finding.source_chunk.chunk_id == chunk.chunk_id
                or finding.matched_chunk.chunk_id == chunk.chunk_id
            ]
            results.append(
                analyzer.analyze_chunk(
                    chunk,
                    heuristic_signals=heuristic_signals,
                    similar_matches=similar_matches,
                    duplicate_findings=relevant_duplicates,
                )
            )
        return results

    def _maybe_write_html_report(
        self,
        result: AuditResultResponse,
        request_config: dict[str, Any],
    ) -> None:
        should_generate = bool(
            request_config.get("include_html_report")
            or request_config.get("enable_html_reports")
            or self.settings.enable_html_reports
        )
        if not should_generate:
            return

        try:
            report_output = write_html_report(result, self.settings.reports_directory)
        except Exception as exc:
            result.warnings.append(f"HTML report generation failed: {exc}")
            return

        result.html_report_path = str(report_output.path)
        result.html_report_url = report_output.url


def run_analysis_job(job_id: str) -> AuditResultResponse | None:
    """Default background task entrypoint used by the API."""

    return AuditPipelineRunner().run(job_id)


def _is_critical_llm_warning(warning: str) -> bool:
    normalized = warning.strip().lower()
    return normalized.startswith(
        (
            "provider_error:",
            "json_repair_provider_error:",
            "invalid_llm_json:",
        )
    )
