"""Static report generation package."""

from app.reports.html_report import HtmlReportOutput, render_html_report, write_html_report

__all__ = ["HtmlReportOutput", "render_html_report", "write_html_report"]
