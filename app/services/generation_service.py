"""Orchestrates QA test-case generation for a selection.

Duplicate-submission policy (assignment explicitly asks for one): submitting
the same selection twice creates a NEW generation record rather than
overwriting the previous one. Generations are append-only history. Rationale:
a prior generation may already be in use / referenced by a user or another
system, and silently overwriting it would be a worse failure mode than
having two records — retrieval always returns all of them, most recent
first, so nothing is hidden, and nothing already handed out is invalidated
by a second submission.
"""
from sqlalchemy.orm import Session

from app.core.exceptions import LLMGenerationError, ValidationFailedError
from app.core.logging import get_logger
from app.llm.client import LLMClient, get_default_client
from app.llm.prompts import build_prompt, build_retry_prompt
from app.llm.repository import GenerationRepository
from app.llm.validator import validate_llm_output
from app.selection.service import get_selection, get_selection_nodes, reconstruct_selection_text

logger = get_logger(__name__)


def generate_test_cases(
    db: Session,
    *,
    selection_id: int,
    llm_client: LLMClient | None = None,
    repository: GenerationRepository | None = None,
) -> dict:
    llm_client = llm_client or get_default_client()
    repository = repository or GenerationRepository()

    selection = get_selection(db, selection_id)
    nodes = get_selection_nodes(db, selection_id)
    selection_text = reconstruct_selection_text(db, selection_id)

    node_hashes = [
        {"logical_node_id": n.logical_node_id, "node_id": n.id, "content_hash": n.content_hash}
        for n in nodes
    ]

    prompt = build_prompt(selection_text)
    raw_response = llm_client.complete(prompt)

    try:
        test_cases = validate_llm_output(raw_response)
    except ValidationFailedError as first_error:
        logger.warning("LLM output failed validation, retrying once: %s", first_error.message)
        retry_prompt = build_retry_prompt(selection_text, raw_response, first_error.message)
        raw_response_retry = llm_client.complete(retry_prompt)
        try:
            test_cases = validate_llm_output(raw_response_retry)
            raw_response = raw_response_retry
            prompt = retry_prompt
        except ValidationFailedError as second_error:
            record = repository.save(
                {
                    "selection_id": selection.id,
                    "document_version_id": selection.document_version_id,
                    "model_name": getattr(llm_client, "model", "unknown"),
                    "status": "FAILED",
                    "prompt": prompt,
                    "raw_response": raw_response_retry,
                    "error": f"Validation failed twice. First: {first_error.message} | Second: {second_error.message}",
                    "test_cases": None,
                    "node_hashes": node_hashes,
                }
            )
            raise LLMGenerationError(
                f"LLM output failed validation after one retry (generation id={record['id']}): "
                f"{second_error.message}"
            ) from second_error

    record = repository.save(
        {
            "selection_id": selection.id,
            "document_version_id": selection.document_version_id,
            "model_name": getattr(llm_client, "model", "unknown"),
            "status": "SUCCESS",
            "prompt": prompt,
            "raw_response": raw_response,
            "error": None,
            "test_cases": [tc.model_dump() for tc in test_cases],
            "node_hashes": node_hashes,
        }
    )
    return record
