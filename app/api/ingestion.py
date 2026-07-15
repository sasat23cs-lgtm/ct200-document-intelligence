from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.document import DocumentVersionOut
from app.schemas.ingest import IngestRequest
from app.services.ingestion_service import ingest_document

router = APIRouter(tags=["ingestion"])


@router.post("/documents/ingest", response_model=DocumentVersionOut, status_code=201)
def ingest(payload: IngestRequest, db: Session = Depends(get_db)):
    """Ingest markdown text as a new version of `document_name`. If a document
    with this name already exists, this creates version N+1 and computes a
    diff against version N — this is the endpoint used to drive the v1 -> v2
    re-ingestion flow described in the README."""
    return ingest_document(
        db,
        document_name=payload.document_name,
        source_filename=payload.source_filename,
        markdown_text=payload.markdown_text,
    )
