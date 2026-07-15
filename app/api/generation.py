from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.generation import GenerateRequest, GenerationOut
from app.services.generation_service import generate_test_cases
from app.services.retrieval_service import attach_staleness

router = APIRouter(tags=["generation"])


@router.post("/selections/{selection_id}/generate", response_model=GenerationOut, status_code=201)
def generate(selection_id: int, db: Session = Depends(get_db)):
    """Generate 3-5 QA test cases from a selection's reconstructed text via
    the LLM, validate the output, and store it. Submitting the same
    selection again creates a new generation record rather than overwriting
    (see app/services/generation_service.py docstring for why)."""
    record = generate_test_cases(db, selection_id=selection_id)
    return attach_staleness(db, record)
