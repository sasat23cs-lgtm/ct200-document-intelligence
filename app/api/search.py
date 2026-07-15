from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.node import NodeSummary
from app.services import browse_service

router = APIRouter(tags=["search"])


@router.get("/search", response_model=list[NodeSummary])
def search(
    q: str = Query(..., min_length=1, description="Substring to search for"),
    scope: Literal["heading", "body", "all"] = Query(default="all"),
    version_id: int | None = Query(default=None, description="Defaults to the latest version"),
    document_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return browse_service.search_nodes(db, query=q, scope=scope, version_id=version_id, document_id=document_id)
