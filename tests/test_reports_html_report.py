"""Tests for static HTML report rendering and API access."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.models.analysis import (
    ImprovementRecommendation,
    MissingContentRecommendation,
    SignalSeverity,
)
from app.models.jobs import JobStatus
from app.models.results import (
    AuditResultResponse,
    AuditSummary,
    DuplicateWarning,
    FailedPageRecord,
    PageAuditResult,
)
from app.reports.html_report import render_html_report, write_html_report
from app.storage import repositories
from app.storage.database import init_db


def _sample_result(job_id: str = "job-123") -> AuditResultResponse:
    return AuditResultResponse(
        job_id=job_id,
        status=JobStatus.PARTIAL,
        message="Audit completed with partial results and warnings.",
        input_url="https://example.com",
        normalized_url="https://example.com",
        summary=AuditSummary(
            pages_analyzed=1,
            pages_failed=1,
            chunks_analyzed=2,
            improvements_count=1,
            missing_content_count=1,
            duplicate_findings_count=1,
            heuristic_signals_count=2,
        ),
        top_priorities=[
            {
                "type": "improvement",
                "page_url": "https://example.com",
                "category": "clarity",
                "severity": "medium",
                "confidence": 0.82,
                "priority_score": 66.8,
                "why_prioritized": (
                    "medium severity; 0.82 confidence; homepage page."
                ),
                "issue": "The homepage headline is vague.",
                "suggested_change": "Name the audience and main value.",
            }
        ],
        pages=[
            PageAuditResult(
                url="https://example.com",
                title="Example Home",
                page_type="homepage",
                summary="1 section; 1 improvement; 1 missing-content suggestion.",
                sections_analyzed=1,
                chunks_analyzed=2,
                improvement_recommendations=[
                    ImprovementRecommendation(
                        category="clarity",
                        page_url="https://example.com",
                        section_id="section-001",
                        section_path=["Hero"],
                        issue="The homepage headline is vague.",
                        suggested_change="Name the audience and main value.",
                        example_text="Audit your website content before launch.",
                        reason="Specific wording helps visitors understand the offer.",
                        severity=SignalSeverity.MEDIUM,
                        confidence=0.82,
                        evidence_snippet="We help websites get better.",
                    )
                ],
                missing_content_recommendations=[
                    MissingContentRecommendation(
                        page_url="https://example.com",
                        section_id="section-001",
                        section_path=["Hero"],
                        recommended_location="Homepage hero",
                        missing_content="Proof point or customer outcome",
                        suggestion_or_outline=(
                            "Add a short result such as faster content reviews."
                        ),
                        reason="Proof improves credibility.",
                        priority=SignalSeverity.MEDIUM,
                        confidence=0.75,
                    )
                ],
                duplicate_warnings=[
                    DuplicateWarning(
                        finding_type="content_overlap",
                        source_chunk_id="chunk-1",
                        matched_chunk_id="chunk-2",
                        matched_page_url="https://example.com/services",
                        similarity_score=0.88,
                        message="Chunks appear to overlap across pages.",
                        evidence_snippet="Repeated service description.",
                    )
                ],
                heuristic_signal_summary={"weak_cta": 1, "thin_section": 1},
            )
        ],
        failed_pages=[
            FailedPageRecord(
                url="https://example.com/missing",
                stage="fetch",
                reason="Unexpected HTTP status 404.",
            )
        ],
        warnings=["Ollama returned invalid JSON for one chunk."],
    )


def test_render_html_report_contains_evaluator_sections():
    html = render_html_report(_sample_result())

    assert "Website Content Auditor Report" in html
    assert "Site Summary" in html
    assert "Top Priorities" in html
    assert "Score 66.8" in html
    assert "medium severity; 0.82 confidence; homepage page." in html
    assert "Improvement Recommendations" in html
    assert "Missing Content Recommendations" in html
    assert "The homepage headline is vague." in html


def test_write_html_report_creates_static_file(tmp_path):
    result = _sample_result()

    output = write_html_report(result, tmp_path)

    assert output.path.exists()
    assert output.url == f"/reports/{result.job_id}"
    assert output.path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_report_route_returns_saved_html_report(tmp_path, monkeypatch):
    db_path = tmp_path / "auditor.db"
    reports_directory = tmp_path / "reports"
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("REPORTS_DIRECTORY", str(reports_directory))
    get_settings.cache_clear()
    init_db(str(db_path))

    result = _sample_result(job_id="job-report-route")
    report_output = write_html_report(result, reports_directory)
    result.html_report_path = str(report_output.path)
    result.html_report_url = report_output.url

    repositories.create_job(
        str(db_path),
        job_id=result.job_id,
        input_url="https://example.com",
        normalized_url="https://example.com",
        status=JobStatus.COMPLETED,
        progress=1.0,
        cache_key=None,
        request_config={},
    )
    repositories.save_audit_result(
        str(db_path),
        job_id=result.job_id,
        result=result.model_dump(mode="json"),
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/reports/{result.job_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Website Content Auditor Report" in response.text

    get_settings.cache_clear()


def test_report_route_returns_404_when_report_file_is_missing(tmp_path, monkeypatch):
    db_path = tmp_path / "auditor.db"
    reports_directory = tmp_path / "reports"
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(db_path))
    monkeypatch.setenv("REPORTS_DIRECTORY", str(reports_directory))
    get_settings.cache_clear()
    init_db(str(db_path))

    result = _sample_result(job_id="job-missing-report")
    result.html_report_path = str(Path(reports_directory) / "missing.html")
    result.html_report_url = f"/reports/{result.job_id}"
    repositories.create_job(
        str(db_path),
        job_id=result.job_id,
        input_url="https://example.com",
        normalized_url="https://example.com",
        status=JobStatus.COMPLETED,
        progress=1.0,
        cache_key=None,
        request_config={},
    )
    repositories.save_audit_result(
        str(db_path),
        job_id=result.job_id,
        result=result.model_dump(mode="json"),
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/reports/{result.job_id}")

    assert response.status_code == 404
    assert response.json()["error"] == "report_not_found"

    get_settings.cache_clear()
