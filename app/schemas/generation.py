from typing import Any

from pydantic import BaseModel, ConfigDict


class GenerateRequest(BaseModel):
    selection_id: int


class NodeStalenessOut(BaseModel):
    logical_node_id: str
    status: str
    reason: str | None = None
    old_hash: str | None = None
    new_hash: str | None = None
    diff_summary: str | None = None


class GenerationOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: int
    selection_id: int
    document_version_id: int
    model_name: str
    status: str
    test_cases: list[dict[str, Any]] | None = None
    error: str | None = None
    generated_at: str
    staleness_status: str | None = None
    compared_against_version: int | None = None
    node_staleness: list[NodeStalenessOut] = []
