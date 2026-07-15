import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class ChangeType(str, enum.Enum):
    NEW = "new"
    MODIFIED = "modified"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class NodeChange(Base):
    """Diff record computed once, at ingestion time, between a DocumentVersion
    and the immediately preceding version of the same document. Only rows
    for NEW/MODIFIED/DELETED are persisted in practice (see versioning/diff.py);
    UNCHANGED is supported in the enum for completeness/testability but is not
    written for every node to avoid an O(n) row explosion on every ingest.
    """

    __tablename__ = "node_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id"), nullable=False
    )  # the NEW version this change record belongs to
    logical_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    change_type: Mapped[ChangeType] = mapped_column(Enum(ChangeType), nullable=False)

    old_node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    new_node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    old_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
