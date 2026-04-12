"""Ollama provider scaffold.

The real HTTP integration with Ollama is intentionally deferred. This class
stores provider configuration so the analysis layer can depend on a stable
interface later.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaProvider:
    """Configuration holder for the future Ollama LLM provider."""

    base_url: str
    model: str
    timeout_seconds: float

    async def generate_json(self, prompt: str) -> dict[str, object]:
        """Placeholder for future Ollama JSON generation."""

        raise NotImplementedError("Ollama calls are not implemented in the scaffold.")

