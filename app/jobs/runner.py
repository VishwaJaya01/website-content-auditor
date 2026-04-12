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
from app.jobs.manager import JobManager
from app.models.analysis import (
    ChunkAnalysisResult,
    ChunkEmbedding,
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
)
from app.models.crawl import CrawlResult, ExtractedPage
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
    ) -> None:
        self.settings = settings or get_settings()
        self.manager = manager or JobManager(self.settings)
        self.discovery_function = discovery_function
        self.embedding_provider = embedding_provider
        self.chunk_analyzer = chunk_analyzer

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

            pages, extraction_failures = self._extract_pages(crawl_result)
            failed_pages.extend(extraction_failures)
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
            warnings.extend(llm_warnings)
            self.manager.update_job_status(job_id, JobStatus.RUNNING, progress=0.9)

            final_status = (
                JobStatus.PARTIAL
                if failed_pages or embedding_warnings or llm_warnings
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
                if partial_job is not None:
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
    ) -> tuple[list[ExtractedPage], list[FailedPageRecord]]:
        pages: list[ExtractedPage] = []
        failed_pages: list[FailedPageRecord] = []

        for fetch_result in crawl_result.fetch_results:
            if not fetch_result.ok:
                failed_pages.append(
                    FailedPageRecord(
                        url=fetch_result.url,
                        reason=fetch_result.error or fetch_result.status.value,
                        stage="fetch",
                    )
                )
                continue

            try:
                page = extract_page(fetch_result)
            except Exception as exc:
                failed_pages.append(
                    FailedPageRecord(
                        url=fetch_result.url,
                        reason=f"Extraction failed: {exc}",
                        stage="extraction",
                    )
                )
                continue

            if page.text_char_count <= 0 or not page.sections:
                failed_pages.append(
                    FailedPageRecord(
                        url=page.url,
                        reason="No meaningful visible text was extracted.",
                        stage="extraction",
                    )
                )
                continue
            pages.append(page)

        return pages, failed_pages

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
