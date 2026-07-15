from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.llm.repository import GenerationRepository
from app.models.document import DocumentVersion
from app.models.node import Node
from app.retrieval.staleness import GenerationStaleness, compute_staleness


def attach_staleness(db: Session, generation: dict) -> dict:
    staleness: GenerationStaleness = compute_staleness(db, generation)
    enriched = dict(generation)
    enriched["staleness_status"] = staleness.status
    enriched["compared_against_version"] = staleness.compared_against_version
    enriched["node_staleness"] = [
        {
            "logical_node_id": n.logical_node_id,
            "status": n.status,
            "reason": n.reason,
            "old_hash": n.old_hash,
            "new_hash": n.new_hash,
            "diff_summary": n.diff_summary,
        }
        for n in staleness.nodes
    ]
    return enriched


def get_testcases_by_selection(
    db: Session, selection_id: int, repository: GenerationRepository | None = None
) -> list[dict]:
    repository = repository or GenerationRepository()
    generations = repository.list_by_selection(selection_id)
    # Most recent first — duplicate submissions are append-only history
    # (see generation_service docstring), so newest is what most callers want.
    generations.sort(key=lambda g: g["id"], reverse=True)
    return [attach_staleness(db, g) for g in generations]


def get_testcases_by_node(
    db: Session, node_id: int, repository: GenerationRepository | None = None
) -> list[dict]:
    """Find all generations (across any selection) whose recorded node hashes
    include this node's logical_node_id, within the same document. Resolving
    by logical_node_id (not the raw node_id) means this also surfaces
    generations created against an OLDER version of this same section."""
    repository = repository or GenerationRepository()

    node = db.get(Node, node_id)
    if node is None:
        raise NotFoundError(f"Node {node_id} not found")

    document_version = db.get(DocumentVersion, node.document_version_id)
    document_id = document_version.document_id

    version_ids_for_document = {
        v.id
        for v in db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).all()
    }

    matches = []
    for generation in repository.list_all():
        if generation.get("document_version_id") not in version_ids_for_document:
            continue
        logical_ids_in_generation = {e["logical_node_id"] for e in generation.get("node_hashes", [])}
        if node.logical_node_id in logical_ids_in_generation:
            matches.append(generation)

    matches.sort(key=lambda g: g["id"], reverse=True)
    return [attach_staleness(db, g) for g in matches]
