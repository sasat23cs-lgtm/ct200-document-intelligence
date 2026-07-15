"""Validates raw LLM text output against the TestCase schema.

Policy (per assignment Feature 7 / Decision Log): never trust raw LLM
output. Validate; on failure, the caller (generation_service) retries once
with the validation error fed back to the model; if that also fails, the
failure is persisted and a clear error is returned. This module only does
the parse+validate step — retry orchestration lives in generation_service so
it can also own prompt construction for the retry.
"""
import json

from pydantic import TypeAdapter, ValidationError

from app.core.exceptions import ValidationFailedError
from app.schemas.testcase import MAX_TEST_CASES, MIN_TEST_CASES, TestCase

_list_adapter = TypeAdapter(list[TestCase])


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop the opening ``` or ```json line and a trailing ``` line if present.
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def validate_llm_output(raw_response: str) -> list[TestCase]:
    """Parse and validate `raw_response` as a list of 3-5 TestCase objects.
    Raises ValidationFailedError with a human-readable message on any
    failure — malformed JSON, wrong shape, missing fields, or a test-case
    count outside [3, 5]."""
    cleaned = strip_code_fences(raw_response)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError(f"LLM response was not valid JSON: {exc}") from exc

    # Be lenient about a top-level {"test_cases": [...]} wrapper — some
    # models add one despite instructions not to — but nothing else.
    if isinstance(parsed, dict) and "test_cases" in parsed:
        parsed = parsed["test_cases"]

    if not isinstance(parsed, list):
        raise ValidationFailedError(
            f"Expected a JSON array of test cases, got {type(parsed).__name__}"
        )

    try:
        test_cases = _list_adapter.validate_python(parsed)
    except ValidationError as exc:
        raise ValidationFailedError(f"Test case schema validation failed: {exc}") from exc

    if not (MIN_TEST_CASES <= len(test_cases) <= MAX_TEST_CASES):
        raise ValidationFailedError(
            f"Expected {MIN_TEST_CASES}-{MAX_TEST_CASES} test cases, got {len(test_cases)}"
        )

    return test_cases
