import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Node(Base):
    """A single node in the parsed document tree, scoped to one DocumentVersion.

    `logical_node_id` is the version-independent identity used for versioning
    and staleness detection (see app/versioning/matcher.py) — it is a
    positional path such as "0.1.0", stable across re-ingestion as long as
    document structure/ordering doesn't change. `id` is the row's own
    version-specific primary key, which is what Selections pin to.
    """

    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    logical_node_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    heading: Mapped[str] = mapped_column(String(500), nullable=False)
    heading_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 0 = synthetic doc root
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id"), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)  # sibling order, document order

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    document_version: Mapped["DocumentVersion"] = relationship(back_populates="nodes")
    parent: Mapped["Node | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Node"]] = relationship(
        back_populates="parent", order_by="Node.order_index"
    )
