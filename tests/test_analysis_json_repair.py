"""Tests for JSON extraction helpers."""

import pytest

from app.analysis.json_repair import (
    JsonParseError,
    extract_json_candidate,
    parse_json_from_text,
)


def test_parse_json_from_text_accepts_valid_json():
    payload = parse_json_from_text('{"improvements": [], "missing_content": []}')

    assert payload == {"improvements": [], "missing_content": []}


def test_parse_json_from_text_extracts_wrapped_json_object():
    payload = parse_json_from_text(
        'Here is the JSON:\n{"warnings": ["ok"], "improvements": []}\nDone.'
    )

    assert payload["warnings"] == ["ok"]


def test_extract_json_candidate_handles_nested_json_and_strings():
    candidate = extract_json_candidate(
        'prefix {"outer": {"message": "keep } inside string"}} suffix'
    )

    assert candidate == '{"outer": {"message": "keep } inside string"}}'


def test_parse_json_from_text_raises_for_text_without_json():
    with pytest.raises(JsonParseError):
        parse_json_from_text("not json at all")
