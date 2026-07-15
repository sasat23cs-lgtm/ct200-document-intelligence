import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", order_by="DocumentVersion.version_number"
    )


class DocumentVersion(Base):
    """A single ingestion of a document. Immutable once created — re-ingesting
    a modified file always inserts a new row here rather than mutating an
    existing one, which is what lets Version 1 selections keep resolving to
    Version 1 text forever."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_doc_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    document: Mapped["Document"] = relationship(back_populates="versions")
    nodes: Mapped[list["Node"]] = relationship(back_populates="document_version")
