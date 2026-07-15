from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.document import DocumentOut, DocumentVersionOut
from app.schemas.node import NodeChangeOut, NodeDetail, NodeSummary
from app.services import browse_service

router = APIRouter(tags=["browse"])


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return browse_service.list_documents(db)


@router.get("/versions", response_model=list[DocumentVersionOut])
def list_versions(document_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    return browse_service.list_versions(db, document_id=document_id)


@router.get("/sections", response_model=list[NodeSummary])
def list_top_level_sections(
    version_id: int | None = Query(default=None, description="Defaults to the latest version"),
    document_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return browse_service.get_top_level_sections(db, version_id=version_id, document_id=document_id)


@router.get("/node/{node_id}", response_model=NodeDetail)
def get_node(node_id: int, db: Session = Depends(get_db)):
    return browse_service.get_node(db, node_id)


@router.get("/node/{node_id}/changes", response_model=NodeChangeOut)
def get_node_changes(node_id: int, db: Session = Depends(get_db)):
    return browse_service.get_node_changes(db, node_id)
