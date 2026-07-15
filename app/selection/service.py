from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.models.node import Node
from app.models.selection import Selection, SelectionNode


def create_selection(db: Session, *, name: str, node_ids: list[int]) -> Selection:
    """Create a named selection pinned to the document version of its nodes.

    All node_ids must belong to the SAME document_version — a selection that
    spans versions would break the "pinned to one version" guarantee the
    assignment requires, so this is rejected explicitly rather than silently
    picking one version to pin to.
    """
    nodes = db.query(Node).filter(Node.id.in_(node_ids)).all()
    found_ids = {n.id for n in nodes}
    missing = set(node_ids) - found_ids
    if missing:
        raise NotFoundError(f"Node id(s) not found: {sorted(missing)}")

    version_ids = {n.document_version_id for n in nodes}
    if len(version_ids) > 1:
        raise ValidationFailedError(
            "All nodes in a selection must belong to the same document version; "
            f"got nodes spanning versions {sorted(version_ids)}."
        )

    selection = Selection(name=name, document_version_id=version_ids.pop())
    db.add(selection)
    db.flush()

    for node in nodes:
        db.add(SelectionNode(selection_id=selection.id, node_id=node.id))

    db.commit()
    db.refresh(selection)
    return selection


def get_selection(db: Session, selection_id: int) -> Selection:
    selection = db.get(Selection, selection_id)
    if selection is None:
        raise NotFoundError(f"Selection {selection_id} not found")
    return selection


def get_selection_nodes(db: Session, selection_id: int) -> list[Node]:
    """Resolve a selection to its actual Node rows. Because SelectionNode.node_id
    points at a specific version-scoped Node primary key (not a logical_node_id),
    this always returns the exact text the selection was created against, even
    if the document has since been re-ingested to a newer version."""
    selection = get_selection(db, selection_id)
    node_ids = [sn.node_id for sn in selection.nodes]
    nodes = db.query(Node).filter(Node.id.in_(node_ids)).all()
    order = {nid: i for i, nid in enumerate(node_ids)}
    return sorted(nodes, key=lambda n: order[n.id])


def reconstruct_selection_text(db: Session, selection_id: int) -> str:
    """Reconstruct the selected nodes' heading+body into a single text block,
    in selection order, for feeding to the LLM prompt."""
    nodes = get_selection_nodes(db, selection_id)
    parts = []
    for node in nodes:
        parts.append(f"{'#' * max(node.heading_level, 1)} {node.heading}\n\n{node.body}".strip())
    return "\n\n".join(parts)
