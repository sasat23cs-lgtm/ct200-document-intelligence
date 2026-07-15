"""Intermediate parse tree, independent of the database layer.

The parser produces a tree of `ParsedNode` objects first; persistence
(app/services/ingestion_service.py) walks this tree afterwards to create
ORM rows. Keeping these separate means the parser can be unit-tested with
zero database involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.hashing import compute_content_hash


@dataclass
class ParsedNode:
    heading: str
    level: int  # 0 = synthetic document root
    body_lines: list[str] = field(default_factory=list)
    parent: "ParsedNode | None" = None
    children: list["ParsedNode"] = field(default_factory=list)
    order_index: int = 0
    logical_node_id: str = ""

    @property
    def body(self) -> str:
        # Strip leading/trailing blank lines but preserve internal blank
        # lines (paragraph breaks, spacing inside tables) exactly as authored.
        lines = self.body_lines
        start = 0
        end = len(lines)
        while start < end and lines[start].strip() == "":
            start += 1
        while end > start and lines[end - 1].strip() == "":
            end -= 1
        return "\n".join(lines[start:end])

    @property
    def content_hash(self) -> str:
        return compute_content_hash(self.heading, self.body)

    def add_child(self, child: "ParsedNode") -> None:
        child.parent = self
        child.order_index = len(self.children)
        self.children.append(child)

    def assign_logical_ids(self, prefix: str = "") -> None:
        """Positional-path logical IDs, e.g. root's 2nd child's 1st child -> '1.0'.
        Stable across re-ingestion as long as document ordering is unchanged —
        this is the chosen version-matching key (see app/versioning/matcher.py)."""
        self.logical_node_id = prefix
        for child in self.children:
            child_prefix = f"{prefix}.{child.order_index}" if prefix else str(child.order_index)
            child.assign_logical_ids(child_prefix)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()
