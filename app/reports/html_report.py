"""Static HTML report rendering for completed audit results."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.models.results import AuditResultResponse

TEMPLATE_NAME = "audit_report.html.j2"


@dataclass(frozen=True)
class HtmlReportOutput:
    """Location metadata for a generated static report."""

    path: Path
    url: str


def render_html_report(result: AuditResultResponse) -> str:
    """Render a complete static HTML report for an audit result."""

    template = _environment().get_template(TEMPLATE_NAME)
    return template.render(result=result)


def write_html_report(
    result: AuditResultResponse,
    reports_directory: str | Path,
) -> HtmlReportOutput:
    """Render and persist a static HTML report under the reports directory."""

    output_directory = Path(reports_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    filename = report_filename(result.job_id)
    output_path = output_directory / filename
    output_path.write_text(render_html_report(result), encoding="utf-8")
    return HtmlReportOutput(path=output_path, url=f"/reports/{result.job_id}")


def report_filename(job_id: str) -> str:
    """Return a safe deterministic report filename for a job ID."""

    safe_job_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", job_id).strip("-")
    return f"{safe_job_id or 'audit-report'}.html"


def _environment() -> Environment:
    template_directory = Path(__file__).parent / "templates"
    return Environment(
        loader=FileSystemLoader(template_directory),
        autoescape=select_autoescape(["html", "xml", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
