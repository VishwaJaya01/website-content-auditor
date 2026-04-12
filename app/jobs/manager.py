"""Synchronous job manager scaffold for future background analysis."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.config import Settings, get_settings
from app.crawler.url_normalizer import normalize_url
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
        normalized_url = self.normalize_request_url(input_url)
        request_config = self.build_request_config(request, normalized_url)
        config_hash = self.request_config_hash(request_config)
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
            request_config=request_config,
        )
        return self._job_from_row(job_row)

    def get_cached_job(self, request: AnalyzeRequest) -> JobResponse | None:
        """Return a completed cached job for this request if available."""

        if request.force_refresh:
            return None

        normalized_url = self.normalize_request_url(str(request.url))
        request_config = self.build_request_config(request, normalized_url)
        cache_key = f"audit:{self.request_config_hash(request_config)}"
        cache_entry = repositories.get_valid_cache_entry(self.db_path, cache_key)
        if cache_entry is None or cache_entry.get("job_id") is None:
            return None

        cached_result = repositories.get_audit_result(
            self.db_path,
            str(cache_entry["job_id"]),
        )
        if cached_result is None:
            return None

        return self.get_job(str(cache_entry["job_id"]))

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

    def mark_partial(
        self,
        job_id: str,
        error_message: str | None = None,
    ) -> JobResponse | None:
        """Mark a job as partially completed."""

        return self.update_job_status(
            job_id,
            JobStatus.PARTIAL,
            progress=1.0,
            error_message=error_message,
        )

    def mark_failed(self, job_id: str, error_message: str) -> JobResponse | None:
        """Mark a job as failed with an error message."""

        return self.update_job_status(
            job_id,
            JobStatus.FAILED,
            progress=1.0,
            error_message=error_message,
        )

    def get_job_request_config(self, job_id: str) -> dict[str, Any]:
        """Return persisted request config for a job."""

        job_row = repositories.get_job(self.db_path, job_id)
        if job_row is None:
            return {}
        raw_config = job_row.get("request_config_json")
        if not isinstance(raw_config, str) or not raw_config:
            return {}
        try:
            parsed = json.loads(raw_config)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def save_cache_entry(self, job: JobResponse) -> None:
        """Persist a cache entry for a completed/partial result."""

        if not job.cache_key:
            return
        config_hash = job.cache_key.removeprefix("audit:")
        repositories.save_cache_entry(
            self.db_path,
            cache_key=job.cache_key,
            normalized_url=job.normalized_url,
            config_hash=config_hash,
            job_id=job.job_id,
            ttl_hours=self.settings.cache_ttl_hours,
        )

    def build_request_config(
        self,
        request: AnalyzeRequest,
        normalized_url: str,
    ) -> dict[str, Any]:
        """Build the stable request config used for cache keys and job running."""

        return {
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
            "embedding_model": self.settings.embedding_model,
            "pipeline_version": "pipeline-v1",
        }

    @staticmethod
    def request_config_hash(request_config: dict[str, Any]) -> str:
        """Return a stable hash for normalized URL plus important config."""

        serialized_config = json.dumps(request_config, sort_keys=True)
        return hashlib.sha256(serialized_config.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_request_url(url: str) -> str:
        return normalize_url(url)

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
