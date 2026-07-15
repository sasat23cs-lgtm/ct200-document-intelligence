import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Selection(Base):
    """A named set of nodes, permanently pinned to the DocumentVersion it was
    created from. Pinning is enforced at two levels: `document_version_id`
    records the version, and every SelectionNode row points at a specific
    version-scoped Node primary key — so even if a later version reuses the
    same logical_node_id, this selection keeps resolving to the original rows.
    """

    __tablename__ = "selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    nodes: Mapped[list["SelectionNode"]] = relationship(back_populates="selection")


class SelectionNode(Base):
    __tablename__ = "selection_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    selection_id: Mapped[int] = mapped_column(ForeignKey("selections.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)

    selection: Mapped["Selection"] = relationship(back_populates="nodes")
