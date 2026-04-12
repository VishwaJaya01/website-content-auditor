# Website Content Auditor

LLM-driven backend system that will crawl websites, analyze visible text content,
and generate structured recommendations for content improvements and missing
sections.

## Current Status

This repository currently contains the initial FastAPI backend scaffold. The API,
configuration system, SQLite storage foundation, job manager, and placeholder
modules are in place.

The real crawler, content extraction, chunking, embeddings, Ollama analysis,
Playwright fallback, and HTML report generation are intentionally deferred to
later implementation steps.

## Planned Architecture

The project is designed as a local-first modular monolith:

- `app/api`: FastAPI routes and HTTP response behavior.
- `app/models`: Pydantic request, job, and result schemas.
- `app/storage`: raw SQLite initialization and repository helpers.
- `app/jobs`: job lifecycle orchestration.
- `app/crawler`: future URL discovery, fetching, filtering, and extraction.
- `app/analysis`: future chunking, heuristics, embeddings, prompts, and aggregation.
- `app/providers`: future LLM provider abstraction, starting with Ollama.
- `app/reports`: future static HTML report generation.
- `app/utils`: shared utility helpers.

## Setup

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

## Run The API

```bash
uvicorn app.main:app --reload
```

The API will initialize the SQLite database at `data/auditor.db` by default.

## Try The Scaffold Endpoints

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Create a scaffold audit job:

```bash
curl -X POST http://127.0.0.1:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","max_pages":3,"max_depth":1}'
```

Check job status:

```bash
curl http://127.0.0.1:8000/jobs/<job_id>
```

Fetch scaffold result:

```bash
curl http://127.0.0.1:8000/results/<job_id>
```

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check .
```

## Assumptions And Limitations

- Ollama is planned as the primary local LLM provider, but no Ollama calls are
  implemented yet.
- The job API currently creates queued scaffold jobs only; no background crawl or
  analysis work is started.
- SQLite is used directly through `sqlite3` to keep the foundation simple and
  appropriate for a solo internship project.
- Cache tables are present, but full cache lookup, TTL enforcement, and result
  reuse are deferred.
