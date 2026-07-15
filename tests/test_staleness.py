import json
import tempfile
from pathlib import Path

import pytest

from app.llm.repository import GenerationRepository
from app.models.node import Node
from app.retrieval.staleness import CURRENT, STALE, compute_staleness
from app.selection.service import create_selection
from app.services.generation_service import generate_test_cases
from app.services.ingestion_service import ingest_document
from app.services.retrieval_service import get_testcases_by_node, get_testcases_by_selection

VALID_TEST_CASE = {
    "title": "Battery low warning appears at threshold",
    "requirement_reference": "2.1.1.1 Battery Life Under Typical Use",
    "objective": "Verify low-battery icon appears at the documented capacity threshold",
    "preconditions": ["Fresh AA batteries installed"],
    "test_steps": ["Discharge battery to just above the documented threshold"],
    "expected_result": "Low-battery icon is not shown above threshold, shown at/below it",
    "priority": "Medium",
}


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.model = "fake-model"

    def complete(self, prompt: str) -> str:
        return self.response


@pytest.fixture()
def _tmp_repo():
    with tempfile.TemporaryDirectory() as tmp:
        yield GenerationRepository(directory=Path(tmp))


class TestStaleness:
    def test_generation_current_when_source_unchanged(self, db_session, _tmp_repo):
        text = open("data/ct200_manual.md").read()
        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=text
        )
        node = (
            db_session.query(Node)
            .filter(Node.document_version_id == v1.id, Node.heading.contains("Overpressure Protection"))
            .one()
        )
        selection = create_selection(db_session, name="Overpressure", node_ids=[node.id])
        client = FakeLLMClient(json.dumps([VALID_TEST_CASE] * 3))
        generate_test_cases(db_session, selection_id=selection.id, llm_client=client, repository=_tmp_repo)

        # No re-ingestion happened -> nothing could have changed.
        [record] = get_testcases_by_selection(db_session, selection.id, repository=_tmp_repo)
        assert record["staleness_status"] == CURRENT
        assert all(n["status"] == "CURRENT" for n in record["node_staleness"])

    def test_generation_stale_after_source_node_modified(self, db_session, _tmp_repo):
        v1_text = open("data/ct200_manual.md").read()
        v2_text = open("data/ct200_manual_v2.md").read()

        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=v1_text
        )
        battery_node = (
            db_session.query(Node)
            .filter(Node.document_version_id == v1.id, Node.heading.contains("Battery Life"))
            .one()
        )
        selection = create_selection(db_session, name="Battery", node_ids=[battery_node.id])
        client = FakeLLMClient(json.dumps([VALID_TEST_CASE] * 3))
        generate_test_cases(db_session, selection_id=selection.id, llm_client=client, repository=_tmp_repo)

        # Re-ingest v2 -- this node's text changed (300->250 cycles).
        ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual_v2.md", markdown_text=v2_text
        )

        [record] = get_testcases_by_selection(db_session, selection.id, repository=_tmp_repo)
        assert record["staleness_status"] == STALE
        [node_status] = record["node_staleness"]
        assert node_status["status"] == STALE
        assert node_status["reason"] == "CONTENT_CHANGED"
        assert node_status["old_hash"] != node_status["new_hash"]
        assert "250 measurement cycles" in node_status["diff_summary"]

    def test_generation_current_after_reingest_if_source_node_untouched(self, db_session, _tmp_repo):
        """Overpressure Protection (4.1) is NOT one of the four nodes that
        change between v1 and v2 -- a generation from it must stay CURRENT
        even after the document is re-ingested."""
        v1_text = open("data/ct200_manual.md").read()
        v2_text = open("data/ct200_manual_v2.md").read()

        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=v1_text
        )
        node = (
            db_session.query(Node)
            .filter(Node.document_version_id == v1.id, Node.heading.contains("Overpressure Protection"))
            .one()
        )
        selection = create_selection(db_session, name="Overpressure", node_ids=[node.id])
        client = FakeLLMClient(json.dumps([VALID_TEST_CASE] * 3))
        generate_test_cases(db_session, selection_id=selection.id, llm_client=client, repository=_tmp_repo)

        ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual_v2.md", markdown_text=v2_text
        )

        [record] = get_testcases_by_selection(db_session, selection.id, repository=_tmp_repo)
        assert record["staleness_status"] == CURRENT

    def test_get_testcases_by_node_finds_generation_via_logical_id(self, db_session, _tmp_repo):
        v1_text = open("data/ct200_manual.md").read()
        v2_text = open("data/ct200_manual_v2.md").read()

        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=v1_text
        )
        battery_node_v1 = (
            db_session.query(Node)
            .filter(Node.document_version_id == v1.id, Node.heading.contains("Battery Life"))
            .one()
        )
        selection = create_selection(db_session, name="Battery", node_ids=[battery_node_v1.id])
        client = FakeLLMClient(json.dumps([VALID_TEST_CASE] * 3))
        generate_test_cases(db_session, selection_id=selection.id, llm_client=client, repository=_tmp_repo)

        v2 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual_v2.md", markdown_text=v2_text
        )
        battery_node_v2 = (
            db_session.query(Node)
            .filter(Node.document_version_id == v2.id, Node.heading.contains("Battery Life"))
            .one()
        )

        # Querying by the NEW version's node id must still surface the
        # generation created against the OLD version's node (same logical id).
        results = get_testcases_by_node(db_session, battery_node_v2.id, repository=_tmp_repo)
        assert len(results) == 1
        assert results[0]["staleness_status"] == STALE

    def test_staleness_reports_source_deleted_for_synthetic_case(self, db_session, _tmp_repo):
        """Real CT-200 data never deletes a node, so this uses a synthetic
        second ingestion to prove SOURCE_DELETED is actually reachable."""
        text_v1 = "# Doc\n\n## A\n\nbody a\n\n## B\n\nbody b\n"
        text_v2 = "# Doc\n\n## A\n\nbody a\n"  # B removed

        v1 = ingest_document(db_session, document_name="Synthetic", source_filename="v1.md", markdown_text=text_v1)
        node_b = db_session.query(Node).filter(Node.document_version_id == v1.id, Node.heading == "B").one()
        selection = create_selection(db_session, name="B selection", node_ids=[node_b.id])
        client = FakeLLMClient(json.dumps([VALID_TEST_CASE] * 3))
        generate_test_cases(db_session, selection_id=selection.id, llm_client=client, repository=_tmp_repo)

        ingest_document(db_session, document_name="Synthetic", source_filename="v2.md", markdown_text=text_v2)

        [record] = get_testcases_by_selection(db_session, selection.id, repository=_tmp_repo)
        assert record["staleness_status"] == STALE
        assert record["node_staleness"][0]["reason"] == "SOURCE_DELETED"
