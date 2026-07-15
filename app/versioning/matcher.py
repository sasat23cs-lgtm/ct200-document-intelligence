"""Version matching: deciding which node in a new document version 'is' which
node in the previous version.

Chosen strategy: POSITIONAL-PATH MATCHING. Two nodes across versions are the
same logical node iff they occupy the identical `logical_node_id` path
(sequence of sibling order_index values from root — assigned by the parser,
see app/parser/models.py).

Why this strategy (full comparison in APPROACH.md):
- Hash-based matching (match nodes with identical content_hash) fails
  immediately for the exact case we most need to detect: a node whose text
  changed. It would report every edited node as "deleted + new" rather than
  "modified".
- Heading-text matching (match nodes with identical heading string) fails on
  this exact document: two nodes are both literally titled "Error Codes"
  (sections 4.2 and 7.1), so naive text matching cannot disambiguate them
  without also considering position — at which point you've reinvented
  positional matching anyway.
- Positional-path matching correctly handles both of those cases because
  identity is defined by structural position, not content or label.

Known limitation (documented honestly): if the document is reordered, or a
section is inserted/removed in the *middle* of a sibling list (shifting the
order_index of everything after it), positional-path matching will
misclassify unrelated nodes as changed/new/deleted. The CT-200 v1->v2 diff
does not reorder anything, so this limitation isn't exercised by the real
fixture, but it's a real failure mode of the chosen approach.
"""
from dataclasses import dataclass

from app.models.node_change import ChangeType


@dataclass
class MatchedNodeInfo:
    logical_node_id: str
    change_type: ChangeType
    old_node_id: int | None
    new_node_id: int | None
    old_hash: str | None
    new_hash: str | None


def match_versions(
    old_nodes: list[dict],
    new_nodes: list[dict],
) -> list[MatchedNodeInfo]:
    """Compare two flat lists of node dicts (each with keys: id, logical_node_id,
    content_hash) and classify every logical_node_id present in either version.

    Only NEW, MODIFIED, and DELETED are returned — UNCHANGED nodes are
    intentionally omitted here to avoid persisting an O(n) row per ingest for
    nodes that didn't change; callers that need the full unchanged set can
    derive it as "everything not in this list".
    """
    old_by_path = {n["logical_node_id"]: n for n in old_nodes}
    new_by_path = {n["logical_node_id"]: n for n in new_nodes}

    all_paths = set(old_by_path) | set(new_by_path)
    results: list[MatchedNodeInfo] = []

    for path in all_paths:
        old_n = old_by_path.get(path)
        new_n = new_by_path.get(path)

        if old_n and not new_n:
            results.append(
                MatchedNodeInfo(path, ChangeType.DELETED, old_n["id"], None, old_n["content_hash"], None)
            )
        elif new_n and not old_n:
            results.append(
                MatchedNodeInfo(path, ChangeType.NEW, None, new_n["id"], None, new_n["content_hash"])
            )
        elif old_n["content_hash"] != new_n["content_hash"]:
            results.append(
                MatchedNodeInfo(
                    path, ChangeType.MODIFIED, old_n["id"], new_n["id"], old_n["content_hash"], new_n["content_hash"]
                )
            )
        # else: unchanged, intentionally not included.

    return results
