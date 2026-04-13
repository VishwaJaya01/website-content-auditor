"""Request and response models for public API endpoints."""

from pydantic import BaseModel, Field, HttpUrl

from app.models.jobs import JobStatus


class AnalyzeRequest(BaseModel):
    """Request body for starting a website audit."""

    url: HttpUrl
    max_pages: int | None = Field(default=None, ge=1, le=100)
    max_depth: int | None = Field(default=None, ge=0, le=10)
    force_refresh: bool = False
    use_playwright_fallback: bool | None = None
    include_html_report: bool = False


class AnalyzeAcceptedResponse(BaseModel):
    """Response returned once an audit job has been accepted."""

    job_id: str
    status: JobStatus
    cached: bool
    status_url: str
    result_url: str


class ApiErrorResponse(BaseModel):
    """Structured error response used for expected API failures."""

    error: str
    message: str
    details: dict[str, object] | None = None

