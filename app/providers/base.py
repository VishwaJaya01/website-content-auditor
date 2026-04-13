"""Thin local-first LLM provider interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMProviderError(RuntimeError):
    """Raised when a provider cannot return usable generated text."""


@dataclass(frozen=True)
class LLMGenerateResponse:
    """Text returned by an LLM provider with light metadata."""

    text: str
    model: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    """Minimal protocol for text generation providers."""

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.1,
        response_format: str | None = "json",
    ) -> LLMGenerateResponse:
        """Generate text for a prompt."""

