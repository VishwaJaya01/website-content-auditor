"""Tests for chunk-level LLM analyzer behavior with fake providers."""

from app.analysis.analyzer import ChunkAnalyzer
from app.models.analysis import (
    ContentChunk,
    ImprovementRecommendation,
    RecommendationCategory,
    SignalSeverity,
)
from app.providers.base import LLMGenerateResponse, LLMProviderError


class FakeProvider:
    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.responses = responses or []
        self.fail = fail
        self.prompts: list[str] = []

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.1,
        response_format: str | None = "json",
    ) -> LLMGenerateResponse:
        self.prompts.append(prompt)
        if self.fail:
            raise LLMProviderError("provider unavailable")
        if not self.responses:
            return LLMGenerateResponse(text="not json", model="fake")
        return LLMGenerateResponse(text=self.responses.pop(0), model="fake")


def _chunk() -> ContentChunk:
    return ContentChunk(
        chunk_id="chunk-001",
        page_url="https://example.com/about",
        page_title="About",
        page_h1="About our team",
        section_id="section-001",
        section_path=["About our team"],
        section_heading="About our team",
        section_heading_level=1,
        chunk_text="We help teams audit content, but the copy is vague.",
        chunk_order=0,
        token_estimate=14,
        text_length=54,
    )


def test_analyzer_validates_and_enriches_valid_json_output():
    provider = FakeProvider(
        [
            """
            {
              "improvements": [
                {
                  "category": "clarity",
                  "issue": "The section says the copy is vague without specifics.",
                  "suggested_change": "Name the exact audience and audit outcome.",
                  "rewrite_example": "We help marketing teams find unclear copy.",
                  "reason": "Specific audience and outcome make the value clearer.",
                  "severity": "medium",
                  "confidence": 0.82,
                  "evidence_snippet": "the copy is vague"
                }
              ],
              "missing_content": [],
              "warnings": []
            }
            """
        ]
    )

    result = ChunkAnalyzer(provider).analyze_chunk(_chunk())

    assert result.chunk_id == "chunk-001"
    assert result.page_url == "https://example.com/about"
    assert result.section_id == "section-001"
    assert len(result.improvements) == 1
    assert result.improvements[0].page_url == result.page_url
    assert result.improvements[0].category == RecommendationCategory.CLARITY
    assert result.improvements[0].example_text.startswith("We help marketing")


def test_analyzer_uses_repair_prompt_after_invalid_json():
    valid_repair = """
    {
      "chunk_id": "chunk-001",
      "page_url": "https://example.com/about",
      "section_id": "section-001",
      "section_path": ["About our team"],
      "improvements": [],
      "missing_content": [
        {
          "missing_content": "A short proof point",
          "suggestion_or_outline": "Add one sentence about who uses the audits.",
          "reason": "Proof makes the claim more credible.",
          "priority": "low",
          "confidence": 0.7
        }
      ],
      "warnings": []
    }
    """
    provider = FakeProvider(["Here is broken JSON:", valid_repair])

    result = ChunkAnalyzer(provider, max_repair_attempts=1).analyze_chunk(_chunk())

    assert len(provider.prompts) == 2
    assert "Repair the following model output" in provider.prompts[1]
    assert len(result.missing_content) == 1
    assert result.missing_content[0].page_url == "https://example.com/about"


def test_analyzer_returns_warning_when_json_stays_invalid():
    provider = FakeProvider(["not json", "still not json"])

    result = ChunkAnalyzer(provider, max_repair_attempts=1).analyze_chunk(_chunk())

    assert result.improvements == []
    assert result.missing_content == []
    assert result.warnings
    assert result.warnings[0].startswith("invalid_llm_json")


def test_analyzer_returns_warning_when_provider_fails():
    provider = FakeProvider(fail=True)

    result = ChunkAnalyzer(provider).analyze_chunk(_chunk())

    assert result.warnings == ["provider_error: provider unavailable"]


def test_legacy_invalid_category_values_load_as_other():
    recommendation = ImprovementRecommendation(
        category="clarity|grammar|tone|cta",
        page_url="https://example.com",
        issue="The section is vague.",
        suggested_change="Use more specific wording.",
        reason="Specific wording improves clarity.",
        severity=SignalSeverity.MEDIUM,
        confidence=0.7,
    )

    assert recommendation.category == RecommendationCategory.OTHER


def test_analyzer_cleans_copied_category_list_and_caps_missing_evidence():
    provider = FakeProvider(
        [
            """
            {
              "improvements": [
                {
                  "category": "clarity|grammar|tone|cta",
                  "issue": "The section has no clear call to action.",
                  "suggested_change": "Add a short contact button.",
                  "reason": "A visible next step helps interested visitors act.",
                  "severity": "high",
                  "confidence": 1.0,
                  "evidence_snippet": ""
                }
              ],
              "missing_content": [],
              "warnings": []
            }
            """
        ]
    )

    result = ChunkAnalyzer(provider).analyze_chunk(_chunk())

    assert len(result.improvements) == 1
    assert result.improvements[0].category == RecommendationCategory.CTA
    assert result.improvements[0].confidence == 0.75
    assert "normalized_copied_category_list" in result.warnings


def test_analyzer_drops_empty_positive_and_generic_model_recommendations():
    provider = FakeProvider(
        [
            """
            {
              "improvements": [
                {
                  "category": "clarity",
                  "issue": "The text is clear and grammatically correct.",
                  "suggested_change": "Add a brief introduction.",
                  "reason": "The text is already strong.",
                  "severity": "medium",
                  "confidence": 1.0
                },
                {
                  "category": "clarity",
                  "issue": "",
                  "suggested_change": "Add clearer copy.",
                  "reason": "Empty issue should be rejected.",
                  "severity": "medium",
                  "confidence": 0.8
                },
                {
                  "category": "readability",
                  "issue": "The section uses vague phrasing.",
                  "suggested_change": "Name the exact audience and outcome.",
                  "reason": "Specific language makes the offer easier to understand.",
                  "severity": "medium",
                  "confidence": 0.8,
                  "evidence_snippet": "We help teams audit content"
                }
              ],
              "missing_content": [
                {
                  "missing_content": "The text is cluttered and hard to read.",
                  "suggestion_or_outline": "Add a generic introduction.",
                  "reason": "Generic placeholder should be rejected.",
                  "priority": "info",
                  "confidence": 1.0
                },
                {
                  "missing_content": "A customer proof point",
                  "suggestion_or_outline": "Add one specific team or use case.",
                  "reason": "Proof makes the claim more credible.",
                  "priority": "medium",
                  "confidence": 0.7
                }
              ],
              "warnings": []
            }
            """
        ]
    )

    result = ChunkAnalyzer(provider).analyze_chunk(_chunk())

    assert len(result.improvements) == 1
    assert result.improvements[0].issue == "The section uses vague phrasing."
    assert len(result.missing_content) == 1
    assert result.missing_content[0].missing_content == "A customer proof point"
    assert "dropped_improvement_without_clear_issue" in result.warnings
    assert "dropped_improvement_missing_required_text" in result.warnings
    assert "dropped_generic_missing_content" in result.warnings
