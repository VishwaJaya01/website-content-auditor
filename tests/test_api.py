"""Smoke tests for the initial FastAPI scaffold."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


def test_health_and_scaffold_job_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "auditor.db"))
    get_settings.cache_clear()

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
        assert result_response.status_code == 200
        assert result_response.json()["status"] == "queued"

    get_settings.cache_clear()

