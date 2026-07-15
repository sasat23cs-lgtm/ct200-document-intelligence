import datetime as dt

from pydantic import BaseModel, ConfigDict


class NodeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    logical_node_id: str
    heading: str
    heading_level: int
    content_hash: str
    order_index: int


class NodeDetail(NodeSummary):
    body: str
    document_version_id: int
    parent_id: int | None
    created_at: dt.datetime
    children: list[NodeSummary] = []


class NodeChangeOut(BaseModel):
    """Response for GET /node/{id}/changes — whether/how a node changed
    relative to the previous version of the same document."""

    logical_node_id: str
    change_type: str
    has_changed: bool
    old_hash: str | None = None
    new_hash: str | None = None
    diff_summary: str | None = None
    compared_old_version: int | None = None
    compared_new_version: int | None = None
