"""Synchronous job manager scaffold for future background analysis."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.config import Settings, get_settings
from app.models.api import AnalyzeRequest
from app.models.jobs import JobResponse, JobStatus
from app.storage import repositories


class JobManager:
    """Create and update audit jobs backed by SQLite."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.sqlite_database_path

    def create_job(self, request: AnalyzeRequest) -> JobResponse:
        """Create a queued scaffold job for a valid analyze request."""

        input_url = str(request.url)
        normalized_url = self._normalize_url(input_url)
        config_hash = self._request_config_hash(request, normalized_url)
        cache_key = f"audit:{config_hash}"
        job_id = str(uuid4())

        job_row = repositories.create_job(
            self.db_path,
            job_id=job_id,
            input_url=input_url,
            normalized_url=normalized_url,
            status=JobStatus.QUEUED,
            progress=0.0,
            cache_key=cache_key,
        )
        return self._job_from_row(job_row)

    def get_job(self, job_id: str) -> JobResponse | None:
        """Return a job if it exists."""

        job_row = repositories.get_job(self.db_path, job_id)
        if job_row is None:
            return None
        return self._job_from_row(job_row)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: float | None = None,
        error_message: str | None = None,
    ) -> JobResponse | None:
        """Update a job status for future pipeline orchestration."""

        job_row = repositories.update_job_status(
            self.db_path,
            job_id,
            status=status,
            progress=progress,
            error_message=error_message,
        )
        if job_row is None:
            return None
        return self._job_from_row(job_row)

    def mark_completed(self, job_id: str) -> JobResponse | None:
        """Mark a job as completed."""

        return self.update_job_status(job_id, JobStatus.COMPLETED, progress=1.0)

    def mark_failed(self, job_id: str, error_message: str) -> JobResponse | None:
        """Mark a job as failed with an error message."""

        return self.update_job_status(
            job_id,
            JobStatus.FAILED,
            progress=1.0,
            error_message=error_message,
        )

    def _request_config_hash(
        self,
        request: AnalyzeRequest,
        normalized_url: str,
    ) -> str:
        effective_config: dict[str, Any] = {
            "normalized_url": normalized_url,
            "max_pages": request.max_pages or self.settings.default_max_pages,
            "max_depth": request.max_depth or self.settings.default_max_depth,
            "use_playwright_fallback": (
                request.use_playwright_fallback
                if request.use_playwright_fallback is not None
                else self.settings.enable_playwright_fallback
            ),
            "include_html_report": request.include_html_report,
            "ollama_model": self.settings.ollama_model,
            "schema_version": "scaffold-v1",
        }
        serialized_config = json.dumps(effective_config, sort_keys=True)
        return hashlib.sha256(serialized_config.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_url(url: str) -> str:
        return url.strip().rstrip("/")

    @staticmethod
    def _job_from_row(row: dict[str, Any]) -> JobResponse:
        return JobResponse(
            job_id=row["job_id"],
            input_url=row["input_url"],
            normalized_url=row["normalized_url"],
            status=JobStatus(row["status"]),
            progress=row["progress"],
            cache_key=row["cache_key"],
            error_message=row["error_message"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
