"""Tests for chunk analysis prompt construction."""

from app.analysis.prompts import build_chunk_analysis_prompt
from app.models.analysis import ContentChunk, HeuristicSignal, SignalSeverity


def _chunk() -> ContentChunk:
    return ContentChunk(
        chunk_id="chunk-001",
        page_url="https://example.com/pricing",
        page_title="Pricing",
        page_h1="Simple pricing",
        section_id="section-001",
        section_path=["Simple pricing", "Plans"],
        section_heading="Plans",
        section_heading_level=2,
        chunk_text=(
            "Our pricing page explains plans but does not include a call to action."
        ),
        chunk_order=0,
        token_estimate=18,
        text_length=75,
    )


def test_prompt_includes_schema_metadata_text_and_relevant_heuristics():
    chunk = _chunk()
    signals = [
        HeuristicSignal(
            signal_type="missing_cta",
            page_url=chunk.page_url,
            section_id=chunk.section_id,
            severity=SignalSeverity.MEDIUM,
            confidence=0.72,
            message="Page may lack a clear call to action.",
            evidence_snippet="does not include a call to action",
        ),
        HeuristicSignal(
            signal_type="thin_page",
            page_url="https://other.example.com",
            severity=SignalSeverity.LOW,
            confidence=0.5,
            message="Irrelevant signal.",
        ),
    ]

    prompt = build_chunk_analysis_prompt(chunk, heuristic_signals=signals)

    assert "Return JSON only" in prompt
    assert '"improvements"' in prompt
    assert '"missing_content"' in prompt
    assert "choose exactly one category" in prompt.lower()
    assert "Never copy the full category list" in prompt
    assert '"category": "clarity"' in prompt
    assert '"page_type": "pricing"' in prompt
    assert "Focus on plan clarity" in prompt
    assert "https://example.com/pricing" in prompt
    assert "Simple pricing" in prompt
    assert "missing_cta" in prompt
    assert "Irrelevant signal" not in prompt
    assert "does not include a call to action" in prompt
