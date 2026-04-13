"""Job-related API and storage models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    """Supported lifecycle states for an audit job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class JobResponse(BaseModel):
    """Public representation of an audit job."""

    job_id: str
    input_url: str
    normalized_url: str
    status: JobStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    cache_key: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

