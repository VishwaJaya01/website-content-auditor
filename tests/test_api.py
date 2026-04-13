"""Smoke tests for the initial FastAPI scaffold."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.models.jobs import JobStatus
from app.models.results import AuditResultResponse
from app.storage import repositories


def test_health_and_scaffold_job_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "auditor.db"))
    get_settings.cache_clear()
    monkeypatch.setattr("app.api.routes.run_analysis_job", lambda job_id: None)

    app = create_app()
    with TestClient(app) as client:
        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "ok"

        analyze_response = client.post(
            "/analyze",
            json={"url": "https://example.com", "max_pages": 3, "max_depth": 1},
        )
        assert analyze_response.status_code == 202
        payload = analyze_response.json()
        assert payload["status"] == "queued"
        assert payload["cached"] is False
        assert payload["job_id"]

        job_response = client.get(payload["status_url"])
        assert job_response.status_code == 200
        assert job_response.json()["job_id"] == payload["job_id"]

        result_response = client.get(payload["result_url"])
        assert result_response.status_code == 202
        assert result_response.json()["status"] == "queued"

        settings = get_settings()
        repositories.save_audit_result(
            settings.sqlite_database_path,
            job_id=payload["job_id"],
            result=AuditResultResponse(
                job_id=payload["job_id"],
                status=JobStatus.COMPLETED,
                message="Audit completed successfully.",
                pages=[],
                warnings=[],
            ).model_dump(mode="json"),
        )
        stored_result_response = client.get(payload["result_url"])
        assert stored_result_response.status_code == 200
        assert stored_result_response.json()["job_id"] == payload["job_id"]
        assert stored_result_response.json()["status"] == "completed"

    get_settings.cache_clear()


def test_analyze_rejects_invalid_url(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "auditor.db"))
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        response = client.post("/analyze", json={"url": "not-a-url"})

    assert response.status_code == 422

    get_settings.cache_clear()
