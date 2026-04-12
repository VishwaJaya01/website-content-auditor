"""Tests for chunk-level LLM analyzer behavior with fake providers."""

from app.analysis.analyzer import ChunkAnalyzer
from app.models.analysis import ContentChunk
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
