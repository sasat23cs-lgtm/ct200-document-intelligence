import pytest

from app.core.exceptions import ValidationFailedError
from app.models.node import Node
from app.selection.service import create_selection, get_selection_nodes, reconstruct_selection_text
from app.services.ingestion_service import ingest_document


class TestSelectionVersionPinning:
    def test_selection_pins_to_creation_version_after_reingest(self, db_session):
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
        selection = create_selection(db_session, name="Battery selection", node_ids=[battery_node_v1.id])
        assert selection.document_version_id == v1.id

        # Re-ingest v2 — must not mutate v1 or the existing selection.
        ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual_v2.md", markdown_text=v2_text
        )

        resolved_nodes = get_selection_nodes(db_session, selection.id)
        assert len(resolved_nodes) == 1
        assert resolved_nodes[0].id == battery_node_v1.id
        # Still the v1 text (300 cycles / 15%), not the v2 text (250 / 10%).
        assert "300 measurement cycles" in resolved_nodes[0].body
        assert "250 measurement cycles" not in resolved_nodes[0].body

    def test_selection_rejects_nodes_spanning_versions(self, db_session):
        v1_text = open("data/ct200_manual.md").read()
        v2_text = open("data/ct200_manual_v2.md").read()

        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=v1_text
        )
        v2 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual_v2.md", markdown_text=v2_text
        )
        node_v1 = db_session.query(Node).filter(Node.document_version_id == v1.id).first()
        node_v2 = db_session.query(Node).filter(Node.document_version_id == v2.id).first()

        with pytest.raises(ValidationFailedError):
            create_selection(db_session, name="Bad selection", node_ids=[node_v1.id, node_v2.id])

    def test_reconstruct_selection_text_includes_heading_and_body(self, db_session):
        text = open("data/ct200_manual.md").read()
        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=text
        )
        node = (
            db_session.query(Node)
            .filter(Node.document_version_id == v1.id, Node.heading.contains("Overpressure"))
            .one()
        )
        selection = create_selection(db_session, name="Overpressure", node_ids=[node.id])
        reconstructed = reconstruct_selection_text(db_session, selection.id)
        assert "Overpressure Protection" in reconstructed
        assert "emergency deflation valve" in reconstructed
