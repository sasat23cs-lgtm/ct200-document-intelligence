from sqlalchemy.orm import Session

from app.core.exceptions import ValidationFailedError
from app.core.logging import get_logger
from app.models.document import Document, DocumentVersion
from app.models.node import Node
from app.models.node_change import NodeChange
from app.parser.markdown_parser import parse_markdown
from app.parser.models import ParsedNode
from app.versioning.matcher import match_versions

logger = get_logger(__name__)


def ingest_document(
    db: Session,
    *,
    document_name: str,
    source_filename: str,
    markdown_text: str,
) -> DocumentVersion:
    """Parse `markdown_text` and persist it as a new version of `document_name`.

    If a Document with this name already exists, this creates version N+1 and
    computes a NodeChange diff against version N (positional-path matching,
    see app/versioning/matcher.py). The previous version's rows are never
    modified — this is what keeps existing Selections resolvable forever.
    """
    document = db.query(Document).filter(Document.name == document_name).one_or_none()
    if document is None:
        document = Document(name=document_name)
        db.add(document)
        db.flush()

    previous_version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )
    next_version_number = (previous_version.version_number + 1) if previous_version else 1

    try:
        parsed_root = parse_markdown(markdown_text, document_title_fallback=document_name)
    except Exception:
        logger.exception("Parsing failed for document=%s source=%s", document_name, source_filename)
        raise

    new_version = DocumentVersion(
        document_id=document.id,
        version_number=next_version_number,
        source_filename=source_filename,
    )
    db.add(new_version)
    db.flush()

    _persist_tree(db, parsed_root, document_version_id=new_version.id, parent_db_id=None)
    db.flush()

    if previous_version is not None:
        _compute_and_store_diff(db, previous_version, new_version)

    db.commit()
    db.refresh(new_version)
    return new_version


def _persist_tree(
    db: Session, node: ParsedNode, *, document_version_id: int, parent_db_id: int | None
) -> None:
    row = Node(
        document_version_id=document_version_id,
        logical_node_id=node.logical_node_id,
        heading=node.heading,
        heading_level=node.level,
        body=node.body,
        parent_id=parent_db_id,
        order_index=node.order_index,
        content_hash=node.content_hash,
    )
    db.add(row)
    db.flush()  # need row.id before persisting children
    for child in node.children:
        _persist_tree(db, child, document_version_id=document_version_id, parent_db_id=row.id)


def _compute_and_store_diff(
    db: Session, old_version: DocumentVersion, new_version: DocumentVersion
) -> None:
    old_nodes = [
        {"id": n.id, "logical_node_id": n.logical_node_id, "content_hash": n.content_hash}
        for n in db.query(Node).filter(Node.document_version_id == old_version.id).all()
    ]
    new_nodes = [
        {"id": n.id, "logical_node_id": n.logical_node_id, "content_hash": n.content_hash}
        for n in db.query(Node).filter(Node.document_version_id == new_version.id).all()
    ]

    changes = match_versions(old_nodes, new_nodes)
    for change in changes:
        db.add(
            NodeChange(
                document_version_id=new_version.id,
                logical_node_id=change.logical_node_id,
                change_type=change.change_type,
                old_node_id=change.old_node_id,
                new_node_id=change.new_node_id,
                old_hash=change.old_hash,
                new_hash=change.new_hash,
            )
        )
    logger.info(
        "Version %s: computed %d change records (new/modified/deleted) vs version %s",
        new_version.version_number,
        len(changes),
        old_version.version_number,
    )


def get_latest_version(db: Session, document_id: int | None = None) -> DocumentVersion:
    query = db.query(DocumentVersion)
    if document_id is not None:
        query = query.filter(DocumentVersion.document_id == document_id)
    version = query.order_by(DocumentVersion.version_number.desc()).first()
    if version is None:
        raise ValidationFailedError("No document versions exist yet. Ingest a document first.")
    return version
