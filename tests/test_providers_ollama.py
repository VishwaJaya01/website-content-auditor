"""Tests for the local Ollama provider without a real Ollama server."""

import json

import httpx
import pytest

from app.providers.base import LLMProviderError
from app.providers.ollama import OllamaProvider


def test_ollama_provider_returns_generated_text_with_mock_transport():
    captured_payload: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={"response": "{\"warnings\": []}", "model": "gemma3:4b"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(
            base_url="http://ollama.test",
            model="gemma3:4b",
            timeout_seconds=1,
            client=client,
        )
        response = provider.generate("Analyze this", temperature=0.2)

    assert response.text == "{\"warnings\": []}"
    assert response.model == "gemma3:4b"
    assert captured_payload["model"] == "gemma3:4b"
    assert captured_payload["format"] == "json"


def test_ollama_provider_wraps_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(base_url="http://ollama.test", client=client)
        with pytest.raises(LLMProviderError, match="HTTP 500"):
            provider.generate("prompt")


def test_ollama_provider_wraps_malformed_response_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(base_url="http://ollama.test", client=client)
        with pytest.raises(LLMProviderError, match="malformed JSON"):
            provider.generate("prompt")


def test_ollama_provider_wraps_empty_generation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": ""}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OllamaProvider(base_url="http://ollama.test", client=client)
        with pytest.raises(LLMProviderError, match="empty generation"):
            provider.generate("prompt")
