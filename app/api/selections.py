from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.selection import SelectionCreate, SelectionOut
from app.selection.service import create_selection, get_selection, get_selection_nodes

router = APIRouter(tags=["selections"])


def _to_out(selection, node_ids: list[int]) -> SelectionOut:
    return SelectionOut(
        id=selection.id,
        name=selection.name,
        document_version_id=selection.document_version_id,
        created_at=selection.created_at,
        node_ids=node_ids,
    )


@router.post("/selections", response_model=SelectionOut, status_code=201)
def create(payload: SelectionCreate, db: Session = Depends(get_db)):
    selection = create_selection(db, name=payload.name, node_ids=payload.node_ids)
    return _to_out(selection, payload.node_ids)


@router.get("/selections/{selection_id}", response_model=SelectionOut)
def get(selection_id: int, db: Session = Depends(get_db)):
    selection = get_selection(db, selection_id)
    nodes = get_selection_nodes(db, selection_id)
    return _to_out(selection, [n.id for n in nodes])
