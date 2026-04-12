"""Repository helpers built on raw sqlite3 connections."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from app.models.jobs import JobStatus
from app.storage.database import get_connection


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def create_job(
    db_path: str,
    *,
    job_id: str,
    input_url: str,
    normalized_url: str,
    status: JobStatus,
    progress: float,
    cache_key: str | None,
) -> dict[str, Any]:
    """Persist a new job and return it as a dictionary."""

    now = _utc_now().isoformat()
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                job_id,
                input_url,
                normalized_url,
                status,
                progress,
                cache_key,
                error_message,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                job_id,
                input_url,
                normalized_url,
                status.value,
                progress,
                cache_key,
                now,
                now,
            ),
        )
    job = get_job(db_path, job_id)
    if job is None:
        raise RuntimeError(f"Failed to create job {job_id}")
    return job


def get_job(db_path: str, job_id: str) -> dict[str, Any] | None:
    """Fetch a job by ID."""

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                job_id,
                input_url,
                normalized_url,
                status,
                progress,
                cache_key,
                error_message,
                created_at,
                updated_at
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
    return _row_to_dict(row)


def update_job_status(
    db_path: str,
    job_id: str,
    *,
    status: JobStatus,
    progress: float | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """Update job lifecycle fields and return the latest job row."""

    now = _utc_now().isoformat()
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE jobs
            SET
                status = ?,
                progress = COALESCE(?, progress),
                error_message = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (status.value, progress, error_message, now, job_id),
        )
    return get_job(db_path, job_id)


def save_audit_result(
    db_path: str,
    *,
    job_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Persist a final audit result JSON payload."""

    now = _utc_now().isoformat()
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO audit_results (
                job_id,
                result_json,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (job_id, json.dumps(result), now),
        )
    stored_result = get_audit_result(db_path, job_id)
    if stored_result is None:
        raise RuntimeError(f"Failed to save result for job {job_id}")
    return stored_result


def get_audit_result(db_path: str, job_id: str) -> dict[str, Any] | None:
    """Fetch a persisted audit result by job ID."""

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT job_id, result_json, created_at
            FROM audit_results
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

    result_row = _row_to_dict(row)
    if result_row is None:
        return None

    return {
        "job_id": result_row["job_id"],
        "result": json.loads(result_row["result_json"]),
        "created_at": result_row["created_at"],
    }


def get_cache_entry(db_path: str, cache_key: str) -> dict[str, Any] | None:
    """Fetch a cache entry by cache key."""

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                cache_key,
                normalized_url,
                config_hash,
                job_id,
                expires_at,
                created_at
            FROM cache_entries
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
    return _row_to_dict(row)
