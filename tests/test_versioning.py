from app.models.node import Node
from app.models.node_change import ChangeType, NodeChange
from app.services.ingestion_service import ingest_document
from app.versioning.matcher import match_versions


class TestMatchVersionsUnit:
    def test_modified_node_detected_by_hash_change(self):
        old = [{"id": 1, "logical_node_id": "0.0", "content_hash": "aaa"}]
        new = [{"id": 2, "logical_node_id": "0.0", "content_hash": "bbb"}]
        [change] = match_versions(old, new)
        assert change.change_type == ChangeType.MODIFIED
        assert change.old_hash == "aaa"
        assert change.new_hash == "bbb"

    def test_unchanged_node_not_returned(self):
        old = [{"id": 1, "logical_node_id": "0.0", "content_hash": "aaa"}]
        new = [{"id": 2, "logical_node_id": "0.0", "content_hash": "aaa"}]
        assert match_versions(old, new) == []

    def test_new_node_detected(self):
        old: list = []
        new = [{"id": 1, "logical_node_id": "0.0", "content_hash": "aaa"}]
        [change] = match_versions(old, new)
        assert change.change_type == ChangeType.NEW
        assert change.old_node_id is None

    def test_deleted_node_detected_synthetic_case(self):
        """The real CT-200 v1->v2 diff never deletes a node, so this synthetic
        fixture is what actually proves deletion detection works."""
        old = [{"id": 1, "logical_node_id": "0.0", "content_hash": "aaa"}]
        new: list = []
        [change] = match_versions(old, new)
        assert change.change_type == ChangeType.DELETED
        assert change.new_node_id is None
        assert change.new_hash is None


class TestIngestionAndDiffIntegration:
    def test_v1_ingest_creates_version_1_with_no_diff(self, db_session):
        text = open("data/ct200_manual.md").read()
        version = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=text
        )
        assert version.version_number == 1
        node_count = db_session.query(Node).filter(Node.document_version_id == version.id).count()
        assert node_count > 20  # sanity: real tree has plenty of nodes
        assert db_session.query(NodeChange).count() == 0  # nothing to diff against yet

    def test_v2_ingest_preserves_v1_and_computes_expected_diff(self, db_session):
        v1_text = open("data/ct200_manual.md").read()
        v2_text = open("data/ct200_manual_v2.md").read()

        v1 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual.md", markdown_text=v1_text
        )
        v2 = ingest_document(
            db_session, document_name="CT-200 Manual", source_filename="ct200_manual_v2.md", markdown_text=v2_text
        )

        assert v2.version_number == 2
        # Version 1 nodes must still exist, untouched.
        v1_nodes = db_session.query(Node).filter(Node.document_version_id == v1.id).all()
        assert len(v1_nodes) > 0

        changes = db_session.query(NodeChange).filter(NodeChange.document_version_id == v2.id).all()
        by_type = {}
        for c in changes:
            by_type.setdefault(c.change_type, []).append(c)

        # Known ground-truth diff (confirmed via `diff -u` during analysis):
        # 2.1.1.1 (battery life), 3.2 (inflation increments), 4.2 (E6 row
        # added), 4.3 (E1-E6 text) are MODIFIED; 5.3 (Data Export) is NEW;
        # nothing is DELETED in the real fixture.
        assert len(by_type.get(ChangeType.MODIFIED, [])) == 4
        assert len(by_type.get(ChangeType.NEW, [])) == 1
        assert ChangeType.DELETED not in by_type

        new_change = by_type[ChangeType.NEW][0]
        new_node = db_session.get(Node, new_change.new_node_id)
        assert "Data Export" in new_node.heading
