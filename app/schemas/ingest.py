from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    document_name: str = Field(..., description="Logical document name, e.g. 'CT-200 Manual'")
    source_filename: str = Field(..., description="Filename this content came from, for provenance")
    markdown_text: str = Field(..., min_length=1)
