"""Initial HTTP routes for the scaffold API."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.jobs.manager import JobManager
from app.models.api import AnalyzeAcceptedResponse, AnalyzeRequest, ApiErrorResponse
from app.models.jobs import JobResponse
from app.models.results import AuditResultResponse
from app.storage import repositories
from app.storage.database import get_connection

router = APIRouter()


def _error_response(status_code: int, error: str, message: str) -> JSONResponse:
    payload = ApiErrorResponse(error=error, message=message)
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
    )


@router.get("/health")
def health() -> dict[str, object]:
    """Return basic service health and storage availability."""

    settings = get_settings()
    storage_available = True
    try:
        with get_connection(settings.sqlite_database_path) as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception:
        storage_available = False

    return {
        "status": "ok",
        "app_name": settings.app_name,
        "version": settings.app_version,
        "storage_available": storage_available,
    }


@router.post(
    "/analyze",
    response_model=AnalyzeAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze(request: AnalyzeRequest) -> AnalyzeAcceptedResponse:
    """Accept an analysis request and create a queued scaffold job."""

    manager = JobManager()
    job = manager.create_job(request)
    return AnalyzeAcceptedResponse(
        job_id=job.job_id,
        status=job.status,
        cached=False,
        status_url=f"/jobs/{job.job_id}",
        result_url=f"/results/{job.job_id}",
    )


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_job(job_id: str) -> JobResponse | JSONResponse:
    """Return metadata for a scaffold audit job."""

    manager = JobManager()
    job = manager.get_job(job_id)
    if job is None:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "job_not_found",
            f"No job exists for id '{job_id}'.",
        )
    return job


@router.get(
    "/results/{job_id}",
    response_model=AuditResultResponse,
    responses={404: {"model": ApiErrorResponse}},
)
def get_result(job_id: str) -> AuditResultResponse | JSONResponse:
    """Return a stored audit result, or a scaffold response for an existing job."""

    settings = get_settings()
    manager = JobManager(settings)
    job = manager.get_job(job_id)
    if job is None:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "job_not_found",
            f"No job exists for id '{job_id}'.",
        )

    stored_result = repositories.get_audit_result(settings.sqlite_database_path, job_id)
    if stored_result is not None:
        return AuditResultResponse.model_validate(stored_result["result"])

    return AuditResultResponse(
        job_id=job.job_id,
        status=job.status,
        message=(
            "Result generation is not implemented yet. The scaffold currently "
            "creates jobs but does not crawl or analyze websites."
        ),
        pages=[],
        warnings=[
            "Crawler, extraction, LLM analysis, and report generation are deferred "
            "to later implementation steps."
        ],
    )

