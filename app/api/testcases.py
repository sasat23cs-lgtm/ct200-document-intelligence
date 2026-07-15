from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.generation import GenerationOut
from app.services import retrieval_service

router = APIRouter(tags=["testcases"])


@router.get("/testcases/{selection_id}", response_model=list[GenerationOut])
def get_by_selection(selection_id: int, db: Session = Depends(get_db)):
    return retrieval_service.get_testcases_by_selection(db, selection_id)


@router.get("/testcases/node/{node_id}", response_model=list[GenerationOut])
def get_by_node(node_id: int, db: Session = Depends(get_db)):
    return retrieval_service.get_testcases_by_node(db, node_id)
