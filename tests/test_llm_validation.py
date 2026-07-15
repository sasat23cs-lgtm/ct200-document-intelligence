import json
import tempfile
from pathlib import Path

import pytest

from app.core.exceptions import LLMGenerationError, ValidationFailedError
from app.llm.repository import GenerationRepository
from app.llm.validator import validate_llm_output
from app.models.node import Node
from app.selection.service import create_selection
from app.services.generation_service import generate_test_cases
from app.services.ingestion_service import ingest_document

VALID_TEST_CASE = {
    "title": "Overpressure triggers emergency deflation",
    "requirement_reference": "4.1 Overpressure Protection",
    "objective": "Verify cuff deflates within 2 seconds above 299 mmHg",
    "preconditions": ["Device powered on", "Cuff attached"],
    "test_steps": ["Simulate cuff pressure exceeding 299 mmHg"],
    "expected_result": "Device vents cuff within 2 seconds and halts inflation",
    "priority": "Critical",
}


class FakeLLMClient:
    """Returns a scripted sequence of responses, one per call."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0
        self.model = "fake-model"

    def complete(self, prompt: str) -> str:
        response = self.responses[self.calls]
        self.calls += 1
        return response


class TestValidateLLMOutput:
    def test_valid_json_array_passes(self):
        raw = json.dumps([VALID_TEST_CASE] * 3)
        result = validate_llm_output(raw)
        assert len(result) == 3

    def test_code_fenced_json_is_stripped(self):
        raw = "```json\n" + json.dumps([VALID_TEST_CASE] * 3) + "\n```"
        result = validate_llm_output(raw)
        assert len(result) == 3

    def test_malformed_json_raises(self):
        with pytest.raises(ValidationFailedError):
            validate_llm_output("this is not json at all {{{")

    def test_too_few_test_cases_raises(self):
        raw = json.dumps([VALID_TEST_CASE] * 2)
        with pytest.raises(ValidationFailedError):
            validate_llm_output(raw)

    def test_too_many_test_cases_raises(self):
        raw = json.dumps([VALID_TEST_CASE] * 6)
        with pytest.raises(ValidationFailedError):
            validate_llm_output(raw)

    def test_missing_required_field_raises(self):
        bad = dict(VALID_TEST_CASE)
        del bad["priority"]
        raw = json.dumps([bad] * 3)
        with pytest.raises(ValidationFailedError):
            validate_llm_output(raw)

    def test_string_test_steps_coerced_to_list(self):
        item = dict(VALID_TEST_CASE)
        item["test_steps"] = "Single step as a string"
        raw = json.dumps([item] * 3)
        result = validate_llm_output(raw)
        assert result[0].test_steps == ["Single step as a string"]


@pytest.fixture()
def _selection(db_session):
    text = open("data/ct200_manual.md").read()
    v1 = ingest_document(
        db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=text
    )
    node = (
        db_session.query(Node)
        .filter(Node.document_version_id == v1.id, Node.heading.contains("Overpressure"))
        .one()
    )
    return create_selection(db_session, name="Overpressure", node_ids=[node.id])


@pytest.fixture()
def _tmp_repo():
    with tempfile.TemporaryDirectory() as tmp:
        yield GenerationRepository(directory=Path(tmp))


class TestGenerationRetryPolicy:
    def test_success_on_first_try(self, db_session, _selection, _tmp_repo):
        client = FakeLLMClient([json.dumps([VALID_TEST_CASE] * 3)])
        record = generate_test_cases(db_session, selection_id=_selection.id, llm_client=client, repository=_tmp_repo)
        assert record["status"] == "SUCCESS"
        assert len(record["test_cases"]) == 3
        assert client.calls == 1

    def test_retries_once_then_succeeds(self, db_session, _selection, _tmp_repo):
        client = FakeLLMClient(["not valid json", json.dumps([VALID_TEST_CASE] * 4)])
        record = generate_test_cases(db_session, selection_id=_selection.id, llm_client=client, repository=_tmp_repo)
        assert record["status"] == "SUCCESS"
        assert len(record["test_cases"]) == 4
        assert client.calls == 2

    def test_fails_after_second_invalid_response(self, db_session, _selection, _tmp_repo):
        client = FakeLLMClient(["not valid json", "still not valid json"])
        with pytest.raises(LLMGenerationError):
            generate_test_cases(db_session, selection_id=_selection.id, llm_client=client, repository=_tmp_repo)
        assert client.calls == 2
        # Failure must be persisted, not silently dropped.
        records = _tmp_repo.list_all()
        assert len(records) == 1
        assert records[0]["status"] == "FAILED"
        assert records[0]["error"] is not None

    def test_duplicate_submission_creates_new_record_not_overwrite(self, db_session, _selection, _tmp_repo):
        client = FakeLLMClient(
            [json.dumps([VALID_TEST_CASE] * 3), json.dumps([VALID_TEST_CASE] * 3)]
        )
        r1 = generate_test_cases(db_session, selection_id=_selection.id, llm_client=client, repository=_tmp_repo)
        r2 = generate_test_cases(db_session, selection_id=_selection.id, llm_client=client, repository=_tmp_repo)
        assert r1["id"] != r2["id"]
        assert len(_tmp_repo.list_by_selection(_selection.id)) == 2
