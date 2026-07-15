from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.document import Document, DocumentVersion
from app.models.node import Node
from app.models.node_change import ChangeType, NodeChange
from app.utils.hashing import normalize_for_search
from app.versioning.diff import summarize_diff


def list_documents(db: Session) -> list[Document]:
    return db.query(Document).order_by(Document.id).all()


def list_versions(db: Session, document_id: int | None = None) -> list[DocumentVersion]:
    query = db.query(DocumentVersion)
    if document_id is not None:
        query = query.filter(DocumentVersion.document_id == document_id)
    return query.order_by(DocumentVersion.document_id, DocumentVersion.version_number).all()


def resolve_version(db: Session, version_id: int | None, document_id: int | None = None) -> DocumentVersion:
    """Resolve a version_id if given, otherwise the latest version (optionally
    scoped to a document_id). Every browse endpoint that takes an optional
    version param goes through here so 'default to latest' is consistent."""
    if version_id is not None:
        version = db.get(DocumentVersion, version_id)
        if version is None:
            raise NotFoundError(f"DocumentVersion {version_id} not found")
        return version

    query = db.query(DocumentVersion)
    if document_id is not None:
        query = query.filter(DocumentVersion.document_id == document_id)
    version = query.order_by(DocumentVersion.version_number.desc()).first()
    if version is None:
        raise NotFoundError("No document versions exist yet")
    return version


def get_top_level_sections(db: Session, version_id: int | None, document_id: int | None = None) -> list[Node]:
    version = resolve_version(db, version_id, document_id)
    # Top-level = the document root's direct children (parent has heading_level 0).
    root = db.query(Node).filter(Node.document_version_id == version.id, Node.heading_level == 0).first()
    if root is None:
        return []
    return (
        db.query(Node)
        .filter(Node.parent_id == root.id)
        .order_by(Node.order_index)
        .all()
    )


def get_node(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise NotFoundError(f"Node {node_id} not found")
    return node


def search_nodes(db: Session, query: str, scope: str, version_id: int | None, document_id: int | None = None) -> list[Node]:
    version = resolve_version(db, version_id, document_id)
    normalized_query = normalize_for_search(query)

    candidates = db.query(Node).filter(Node.document_version_id == version.id).all()
    results = []
    for node in candidates:
        haystacks = []
        if scope in ("heading", "all"):
            haystacks.append(normalize_for_search(node.heading))
        if scope in ("body", "all"):
            haystacks.append(normalize_for_search(node.body))
        if any(normalized_query in h for h in haystacks):
            results.append(node)
    return results


def get_node_changes(db: Session, node_id: int) -> dict:
    """Determine whether `node_id` changed relative to the previous version of
    the same document. Works by finding the NodeChange row (if any) recorded
    against this node's logical_node_id when its version was ingested.
    """
    node = get_node(db, node_id)
    version = db.get(DocumentVersion, node.document_version_id)

    change = (
        db.query(NodeChange)
        .filter(
            NodeChange.document_version_id == version.id,
            NodeChange.logical_node_id == node.logical_node_id,
        )
        .one_or_none()
    )

    previous_version = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.version_number < version.version_number,
        )
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )

    if change is None:
        # No change record -> either this is version 1 (nothing to compare
        # against) or the node was unchanged (we don't persist UNCHANGED rows).
        return {
            "logical_node_id": node.logical_node_id,
            "change_type": ChangeType.UNCHANGED.value if previous_version else "not_applicable",
            "has_changed": False,
            "old_hash": None,
            "new_hash": node.content_hash,
            "diff_summary": None,
            "compared_old_version": previous_version.version_number if previous_version else None,
            "compared_new_version": version.version_number,
        }

    diff_summary = None
    if change.change_type == ChangeType.MODIFIED and change.old_node_id:
        old_node = db.get(Node, change.old_node_id)
        diff_summary = summarize_diff(old_node.body, node.body)
    elif change.change_type == ChangeType.NEW:
        diff_summary = "Node did not exist in the previous version."
    elif change.change_type == ChangeType.DELETED:
        diff_summary = "Node was removed in this version."

    return {
        "logical_node_id": node.logical_node_id,
        "change_type": change.change_type.value,
        "has_changed": change.change_type != ChangeType.UNCHANGED,
        "old_hash": change.old_hash,
        "new_hash": change.new_hash,
        "diff_summary": diff_summary,
        "compared_old_version": previous_version.version_number if previous_version else None,
        "compared_new_version": version.version_number,
    }
