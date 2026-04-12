"""Local Ollama provider implementation."""

from __future__ import annotations

import httpx

from app.config import Settings, get_settings
from app.providers.base import LLMGenerateResponse, LLMProviderError


class OllamaProvider:
    """Synchronous Ollama client for local LLM generation."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        active_settings = settings or get_settings()
        self.base_url = (base_url or active_settings.ollama_base_url).rstrip("/")
        self.model = model or active_settings.ollama_model
        self.timeout_seconds = (
            timeout_seconds or active_settings.request_timeout_seconds
        )
        self.client = client

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.1,
        response_format: str | None = "json",
    ) -> LLMGenerateResponse:
        """Generate text from local Ollama and wrap provider failures."""

        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if response_format:
            payload["format"] = response_format

        try:
            response = self._post_generate(payload)
        except httpx.TimeoutException as exc:
            raise LLMProviderError(f"Ollama request timed out: {exc}") from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(f"Could not connect to Ollama: {exc}") from exc

        if response.status_code != 200:
            raise LLMProviderError(
                f"Ollama returned HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMProviderError(
                "Ollama returned a malformed JSON response."
            ) from exc

        generated_text = data.get("response")
        if not isinstance(generated_text, str) or not generated_text.strip():
            raise LLMProviderError("Ollama returned an empty generation response.")

        return LLMGenerateResponse(
            text=generated_text.strip(),
            model=str(data.get("model") or self.model),
            raw=data,
        )

    def _post_generate(self, payload: dict[str, object]) -> httpx.Response:
        endpoint = f"{self.base_url}/api/generate"
        if self.client is not None:
            return self.client.post(
                endpoint,
                json=payload,
                timeout=self.timeout_seconds,
            )

        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.post(endpoint, json=payload)
