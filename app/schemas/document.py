import datetime as dt

from pydantic import BaseModel, ConfigDict


class DocumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_number: int
    source_filename: str
    ingested_at: dt.datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: dt.datetime
    versions: list[DocumentVersionOut] = []
