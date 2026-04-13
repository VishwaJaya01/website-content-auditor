"""Small JSON extraction and repair helpers for local LLM output."""

from __future__ import annotations

import json
from typing import Any

from app.analysis.prompts import build_json_repair_prompt
from app.providers.base import LLMProvider


class JsonParseError(ValueError):
    """Raised when model output cannot be parsed as JSON."""


def parse_json_from_text(text: str) -> Any:
    """Parse JSON directly, then by extracting the first balanced JSON value."""

    stripped = text.strip()
    if not stripped:
        raise JsonParseError("Model output is empty.")

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        candidate = extract_json_candidate(stripped)
        if candidate is None:
            raise JsonParseError(
                "No JSON object or array found in model output."
            ) from None
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise JsonParseError(f"Extracted JSON is invalid: {exc}") from exc


def extract_json_candidate(text: str) -> str | None:
    """Extract the first balanced JSON object or array from text."""

    start_index = _find_json_start(text)
    if start_index is None:
        return None

    opening = text[start_index]
    closing = "}" if opening == "{" else "]"
    stack = [closing]
    in_string = False
    escape_next = False

    for index in range(start_index + 1, len(text)):
        char = text[index]
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char in "{[":
            stack.append("}" if char == "{" else "]")
            continue
        if char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return text[start_index : index + 1]
    return None


def repair_json_output(
    *,
    invalid_output: str,
    provider: LLMProvider,
    validation_error: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Ask the provider once to repair invalid JSON output."""

    repair_prompt = build_json_repair_prompt(
        invalid_output=invalid_output,
        validation_error=validation_error,
    )
    return provider.generate(
        repair_prompt,
        temperature=temperature,
        response_format="json",
    ).text


def _find_json_start(text: str) -> int | None:
    object_index = text.find("{")
    array_index = text.find("[")
    candidates = [index for index in (object_index, array_index) if index >= 0]
    if not candidates:
        return None
    return min(candidates)
