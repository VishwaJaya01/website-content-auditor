"""Base interfaces for future LLM providers."""

from typing import Protocol


class LLMProvider(Protocol):
    """Minimal protocol for structured text generation providers."""

    async def generate_json(self, prompt: str) -> dict[str, object]:
        """Generate a JSON-like response for a prompt."""

