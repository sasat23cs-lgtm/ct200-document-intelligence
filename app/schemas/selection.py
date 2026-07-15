import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class SelectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    node_ids: list[int] = Field(..., min_length=1)


class SelectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    document_version_id: int
    created_at: dt.datetime
    node_ids: list[int]
