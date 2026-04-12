# Website Content Auditor

Website Content Auditor is a local-first FastAPI backend for auditing website
content with a hybrid ML pipeline. It accepts a website URL, crawls meaningful
same-domain pages, extracts visible content, chunks it by section, runs
deterministic heuristics and similarity checks, analyzes chunks with a local
Ollama LLM, and returns structured recommendations grouped by page.

The project is designed as an internship-quality backend submission: small
enough to run locally, but structured like a production-minded content analysis
system instead of a single "scrape text and prompt an LLM" script.

## Core Features

- FastAPI JSON API with job-based analysis flow.
- Same-domain URL normalization, filtering, prioritization, and HTML fetching.
- Boilerplate-aware visible text extraction with heading-aware sections.
- Section-aware chunking for later LLM analysis.
- Rule-based heuristic signals for thin content, weak CTAs, vague wording,
  weak structure, trust gaps, and repetition.
- Local sentence-transformers embeddings for similarity retrieval and
  cross-page duplicate or overlap detection.
- Local Ollama provider, defaulting to `gemma3:4b`.
- Strict Pydantic schemas for chunk-level LLM recommendations.
- JSON parsing, extraction, and bounded repair for imperfect model output.
- SQLite-backed jobs, results, and cache entries.
- Static HTML report generation for completed or partial audits.

## Architecture

The app is a modular monolith under `app/`:

```text
app/
├── api/          # FastAPI routes
├── analysis/     # chunking, heuristics, embeddings, prompts, LLM analysis, aggregation
├── crawler/      # URL normalization, filtering, discovery, fetching, extraction
├── jobs/         # job lifecycle and pipeline runner
├── models/       # Pydantic API and domain schemas
├── providers/    # LLM provider interface and Ollama implementation
├── reports/      # static HTML report rendering
├── storage/      # SQLite initialization and repository helpers
└── utils/        # shared text/logging utilities
```

Pipeline flow:

1. `POST /analyze` validates the request and creates or reuses a job.
2. The background runner checks cache, crawls same-domain pages, and fetches HTML.
3. Extracted pages are converted into heading-aware sections.
4. Sections become analysis-ready chunks.
5. Heuristics and embeddings produce supporting signals and duplicate findings.
6. Ollama analyzes each chunk and returns structured recommendations.
7. Aggregation deduplicates and groups findings by page.
8. The final JSON result is saved in SQLite.
9. A static HTML report is generated when enabled or requested.

## Requirements

- Python 3.11+
- Ollama running locally
- `gemma3:4b` pulled in Ollama
- Internet access the first time `sentence-transformers/all-MiniLM-L6-v2` is
  downloaded, unless the model is already cached locally

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Install and prepare Ollama:

```bash
ollama pull gemma3:4b
ollama serve
```

In another terminal, run the API:

```bash
uvicorn app.main:app --reload
```

By default, SQLite data is stored at `data/auditor.db` and generated reports are
stored under `reports/`. Both are ignored by git.

## Environment

Common settings in `.env`:

```env
SQLITE_DATABASE_PATH="data/auditor.db"
OLLAMA_BASE_URL="http://localhost:11434"
OLLAMA_MODEL="gemma3:4b"
EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_MAX_PAGES=8
DEFAULT_MAX_DEPTH=2
CACHE_TTL_HOURS=24
ENABLE_HTML_REPORTS=true
REPORTS_DIRECTORY="reports"
```

`ENABLE_PLAYWRIGHT_FALLBACK` is present for future expansion, but Playwright is
not implemented in this version.

## API Usage

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Start an audit:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "max_pages": 5,
    "max_depth": 2,
    "force_refresh": false,
    "include_html_report": true
  }'
```

The response includes a `job_id` plus status and result URLs:

```json
{
  "job_id": "b2f6c6d7-...",
  "status": "queued",
  "cached": false,
  "status_url": "/jobs/b2f6c6d7-...",
  "result_url": "/results/b2f6c6d7-..."
}
```

Check job status:

```bash
curl http://127.0.0.1:8000/jobs/<job_id>
```

Fetch JSON results:

```bash
curl http://127.0.0.1:8000/results/<job_id>
```

Fetch the HTML report:

```bash
curl http://127.0.0.1:8000/reports/<job_id> -o audit-report.html
```

Open `audit-report.html` in a browser, or open the saved file listed in
`html_report_path` from the JSON result.

## Output Shape

Final results include:

- job metadata and generation timestamp
- input and normalized URL
- site-level summary counts
- top priorities
- page-level grouped recommendations
- missing-content recommendations
- duplicate or overlap warnings
- heuristic signal summaries
- crawl, extraction, embedding, or LLM warnings
- optional `html_report_path` and `html_report_url`

## Caching Behavior

The cache key is derived from the normalized URL and important request/runtime
configuration such as crawl limits, Ollama model, embedding model, and pipeline
version. If a valid cached result exists and `force_refresh` is false,
`POST /analyze` returns the cached job instead of reprocessing the site.

Cache entries expire after `CACHE_TTL_HOURS`.

## Reports

HTML reports are generated for completed and partial jobs when:

- `include_html_report` is true on the request, or
- `ENABLE_HTML_REPORTS=true` in environment settings

Reports are static HTML files rendered with Jinja2. They do not require
JavaScript or a frontend build step.

## Development

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check .
```

Compile-check imports:

```bash
python -m compileall app tests
```

## Assumptions

- The system is intended for small to moderate websites, not full enterprise
  crawls.
- Ollama must be running locally for real LLM analysis.
- The embedding model may download on first use.
- Crawling is same-domain only.
- JavaScript-heavy pages may produce limited content until Playwright fallback is
  implemented.

## Limitations

- No Playwright fallback yet.
- No competitor comparison mode.
- No remote paid provider support.
- No vector database or distributed queue.
- LLM output quality depends on the local model and source page quality.
- The current background execution uses FastAPI background tasks, which is
  appropriate for a local demo but not a production queue.

## Future Improvements

- Optional Playwright fallback for JS-heavy websites.
- HTML report theming or export bundles.
- More page-type-aware prompt variants.
- Richer site-level prioritization.
- Optional remote provider implementation behind the existing provider interface.
