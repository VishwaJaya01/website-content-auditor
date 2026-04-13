"""Chunk-level LLM analysis orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from app.analysis.json_repair import (
    JsonParseError,
    parse_json_from_text,
    repair_json_output,
)
from app.analysis.output_quality import (
    clean_improvement_payload,
    clean_missing_content_payload,
)
from app.analysis.prompts import build_chunk_analysis_prompt
from app.models.analysis import (
    ChunkAnalysisResult,
    ContentChunk,
    DuplicateContentFinding,
    HeuristicSignal,
    SignalSeverity,
    SimilarChunkMatch,
)
from app.providers.base import LLMProvider, LLMProviderError

DEFAULT_REPAIR_ATTEMPTS = 1


class ChunkAnalyzer:
    """Analyze one chunk with an LLM provider and validated JSON output."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        temperature: float = 0.1,
        max_repair_attempts: int = DEFAULT_REPAIR_ATTEMPTS,
    ) -> None:
        self.provider = provider
        self.temperature = temperature
        self.max_repair_attempts = max_repair_attempts

    def analyze_chunk(
        self,
        chunk: ContentChunk,
        *,
        heuristic_signals: Sequence[HeuristicSignal] | None = None,
        similar_matches: Sequence[SimilarChunkMatch] | None = None,
        duplicate_findings: Sequence[DuplicateContentFinding] | None = None,
    ) -> ChunkAnalysisResult:
        """Run prompt generation, provider call, parse, repair, and validation."""

        prompt = build_chunk_analysis_prompt(
            chunk,
            heuristic_signals=heuristic_signals,
            similar_matches=similar_matches,
            duplicate_findings=duplicate_findings,
        )

        try:
            raw_output = self.provider.generate(
                prompt,
                temperature=self.temperature,
                response_format="json",
            ).text
        except LLMProviderError as exc:
            return _failure_result(chunk, f"provider_error: {exc}")

        last_error: str | None = None
        for attempt in range(self.max_repair_attempts + 1):
            try:
                payload = parse_json_from_text(raw_output)
                payload = _enrich_payload(payload, chunk)
                return ChunkAnalysisResult.model_validate(payload)
            except (JsonParseError, ValidationError, ValueError) as exc:
                last_error = str(exc)
                if attempt >= self.max_repair_attempts:
                    break
                try:
                    raw_output = repair_json_output(
                        invalid_output=raw_output,
                        provider=self.provider,
                        validation_error=last_error,
                        temperature=0.0,
                    )
                except LLMProviderError as repair_exc:
                    return _failure_result(
                        chunk,
                        f"json_repair_provider_error: {repair_exc}",
                    )

        return _failure_result(
            chunk,
            f"invalid_llm_json: {last_error or 'unknown validation error'}",
        )


def analyze_chunk_with_provider(
    chunk: ContentChunk,
    provider: LLMProvider,
    *,
    heuristic_signals: Sequence[HeuristicSignal] | None = None,
    similar_matches: Sequence[SimilarChunkMatch] | None = None,
    duplicate_findings: Sequence[DuplicateContentFinding] | None = None,
    temperature: float = 0.1,
    max_repair_attempts: int = DEFAULT_REPAIR_ATTEMPTS,
) -> ChunkAnalysisResult:
    """Convenience function for one-off chunk analysis."""

    analyzer = ChunkAnalyzer(
        provider,
        temperature=temperature,
        max_repair_attempts=max_repair_attempts,
    )
    return analyzer.analyze_chunk(
        chunk,
        heuristic_signals=heuristic_signals,
        similar_matches=similar_matches,
        duplicate_findings=duplicate_findings,
    )


def _enrich_payload(payload: Any, chunk: ContentChunk) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = {"improvements": payload, "missing_content": [], "warnings": []}
    if not isinstance(payload, dict):
        raise ValueError("LLM output must be a JSON object.")

    payload["chunk_id"] = chunk.chunk_id
    payload["page_url"] = chunk.page_url
    payload["section_id"] = chunk.section_id
    payload["section_path"] = chunk.section_path
    payload.setdefault("improvements", [])
    payload.setdefault("missing_content", [])
    payload.setdefault("warnings", [])
    if not isinstance(payload["warnings"], list):
        payload["warnings"] = [str(payload["warnings"])]
    warnings = [str(warning) for warning in payload["warnings"]]

    improvements: list[dict[str, Any]] = []
    for item in payload.get("improvements", []):
        if not isinstance(item, dict):
            continue
        cleaned = _enrich_improvement(item, chunk, warnings=warnings)
        if cleaned is not None:
            improvements.append(cleaned)

    missing_content: list[dict[str, Any]] = []
    for item in payload.get("missing_content", []):
        if not isinstance(item, dict):
            continue
        cleaned = _enrich_missing_content(item, chunk, warnings=warnings)
        if cleaned is not None:
            missing_content.append(cleaned)

    payload["improvements"] = improvements
    payload["missing_content"] = missing_content
    payload["warnings"] = _dedupe_warnings(warnings)
    return payload


def _enrich_improvement(
    item: dict[str, Any],
    chunk: ContentChunk,
    *,
    warnings: list[str],
) -> dict[str, Any] | None:
    enriched = dict(item)
    enriched["page_url"] = chunk.page_url
    enriched["section_id"] = chunk.section_id
    enriched["section_path"] = chunk.section_path
    if "rewrite_example" in enriched and "example_text" not in enriched:
        enriched["example_text"] = enriched["rewrite_example"]
    enriched.setdefault("category", "other")
    enriched.setdefault("severity", SignalSeverity.MEDIUM.value)
    enriched.setdefault("confidence", 0.6)
    return clean_improvement_payload(enriched, warnings=warnings)


def _enrich_missing_content(
    item: dict[str, Any],
    chunk: ContentChunk,
    *,
    warnings: list[str],
) -> dict[str, Any] | None:
    enriched = dict(item)
    enriched["page_url"] = chunk.page_url
    enriched["section_id"] = chunk.section_id
    enriched["section_path"] = chunk.section_path
    if "suggestion" in enriched and "suggestion_or_outline" not in enriched:
        enriched["suggestion_or_outline"] = enriched["suggestion"]
    if "severity" in enriched and "priority" not in enriched:
        enriched["priority"] = enriched["severity"]
    enriched.setdefault("priority", SignalSeverity.MEDIUM.value)
    enriched.setdefault("confidence", 0.6)
    return clean_missing_content_payload(enriched, warnings=warnings)


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped


def _failure_result(chunk: ContentChunk, warning: str) -> ChunkAnalysisResult:
    return ChunkAnalysisResult(
        chunk_id=chunk.chunk_id,
        page_url=chunk.page_url,
        section_id=chunk.section_id,
        section_path=chunk.section_path,
        warnings=[warning],
    )
