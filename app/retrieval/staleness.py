"""Staleness / impact detection (Feature 9 — the core requirement).

A generation was created from specific node content, captured at generation
time as a list of (logical_node_id, node_id, content_hash) triples. At
retrieval time, we recompute: for each of those triples, what is the
CURRENT node with that logical_node_id in the document's latest version, and
does its content_hash still match?

Honesty about limits (see APPROACH.md): this is a binary hash comparison.
It cannot distinguish a cosmetic wording fix from a safety-relevant
change (e.g. CT-200 3.2's inflation increment 40mmHg -> 30mmHg) — both flip
a node from CURRENT to STALE identically. A one-word typo fix produces
exactly the same STALE signal as a changed pressure threshold. We flag
*that a review is needed*, not *how urgently* — a human still has to look.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.document import DocumentVersion
from app.models.node import Node
from app.versioning.diff import summarize_diff

CURRENT = "CURRENT"
STALE = "STALE"


@dataclass
class NodeStaleness:
    logical_node_id: str
    status: str
    reason: str | None
    old_hash: str | None
    new_hash: str | None
    diff_summary: str | None


@dataclass
class GenerationStaleness:
    status: str
    compared_against_version: int | None
    nodes: list[NodeStaleness] = field(default_factory=list)


def compute_staleness(db: Session, generation: dict) -> GenerationStaleness:
    document_version = db.get(DocumentVersion, generation["document_version_id"])
    if document_version is None:
        # The version this generation was created from no longer exists in
        # the DB at all (shouldn't happen since versions are never deleted,
        # but handled explicitly rather than raising an unhandled exception).
        return GenerationStaleness(status=STALE, compared_against_version=None, nodes=[])

    latest_version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_version.document_id)
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )

    node_statuses: list[NodeStaleness] = []
    any_stale = False

    for entry in generation.get("node_hashes", []):
        logical_id = entry["logical_node_id"]
        old_hash = entry["content_hash"]
        old_node_pk = entry.get("node_id")

        current_node = (
            db.query(Node)
            .filter(Node.document_version_id == latest_version.id, Node.logical_node_id == logical_id)
            .one_or_none()
        )

        if current_node is None:
            any_stale = True
            node_statuses.append(
                NodeStaleness(
                    logical_node_id=logical_id,
                    status=STALE,
                    reason="SOURCE_DELETED",
                    old_hash=old_hash,
                    new_hash=None,
                    diff_summary="This section no longer exists in the latest document version.",
                )
            )
        elif current_node.content_hash != old_hash:
            any_stale = True
            old_node = db.get(Node, old_node_pk) if old_node_pk else None
            diff_summary = (
                summarize_diff(old_node.body, current_node.body)
                if old_node is not None
                else "Source text changed (original node text unavailable for diff)."
            )
            node_statuses.append(
                NodeStaleness(
                    logical_node_id=logical_id,
                    status=STALE,
                    reason="CONTENT_CHANGED",
                    old_hash=old_hash,
                    new_hash=current_node.content_hash,
                    diff_summary=diff_summary,
                )
            )
        else:
            node_statuses.append(
                NodeStaleness(
                    logical_node_id=logical_id,
                    status=CURRENT,
                    reason=None,
                    old_hash=old_hash,
                    new_hash=current_node.content_hash,
                    diff_summary=None,
                )
            )

    overall_status = STALE if any_stale else CURRENT
    return GenerationStaleness(
        status=overall_status,
        compared_against_version=latest_version.version_number,
        nodes=node_statuses,
    )
