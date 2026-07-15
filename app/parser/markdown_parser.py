"""Line-based markdown parser, purpose-built for the CT-200 manual family.

This is intentionally NOT a general CommonMark parser (explicitly out of
scope per the assignment). It handles exactly the constructs present in
this document: ATX headings (# .. ######), HTML comments, GFM pipe tables,
numbered/bulleted lists, and plain paragraphs — and it fails loudly
(ParserError) on structures it cannot confidently interpret, rather than
guessing.

Design decision (see APPROACH.md for full rationale): tree structure is
determined SOLELY by markdown heading depth (number of leading '#'
characters). The numeric prefixes inside heading text (e.g. "2.1.1.1") are
stored verbatim as part of the heading string but are NEVER parsed or used
to infer nesting or sibling order — the source document contains headings
where the label's numbering does not match its actual markdown depth
(2.1.1.1 is only one level below 2.1) and headings that are out of numeric
order in the file (3.4 appears before 3.3). Trusting heading depth and
document order is the only strategy that doesn't silently mis-parent or
misorder those nodes.
"""
import re

from app.parser.exceptions import EmptyDocumentError, MalformedTableError
from app.parser.models import ParsedNode

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def parse_markdown(text: str, document_title_fallback: str = "Document") -> ParsedNode:
    """Parse raw markdown text into a tree of ParsedNode, rooted at a synthetic
    document-root node (level 0). Raises ParserError subclasses on structures
    the parser cannot confidently handle."""
    lines = text.replace("\r\n", "\n").split("\n")

    root = ParsedNode(heading=document_title_fallback, level=0)
    stack: list[ParsedNode] = [root]  # stack[-1] = deepest currently-open node

    i = 0
    n = len(lines)
    saw_any_heading = False

    while i < n:
        line = lines[i]
        heading_match = _HEADING_RE.match(line)

        if heading_match:
            saw_any_heading = True
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)

            # Pop the stack until we find the nearest open ancestor with a
            # strictly smaller level than this heading. This is what makes
            # depth-as-truth deterministic even when numeric labels disagree
            # with actual nesting (see module docstring).
            while stack and stack[-1].level >= level:
                stack.pop()
            if not stack:
                # Cannot happen in practice since root is level 0 and always
                # stays at the bottom, but guard defensively rather than
                # silently attaching to nothing.
                stack = [root]

            parent = stack[-1]
            node = ParsedNode(heading=heading_text, level=level)
            parent.add_child(node)
            stack.append(node)
            i += 1
            continue

        # Table block: a contiguous run of lines starting with a pipe-row
        # followed immediately by a valid GFM separator row.
        if _TABLE_ROW_RE.match(line) and i + 1 < n and _TABLE_SEPARATOR_RE.match(lines[i + 1]) and "-" in lines[i + 1]:
            table_lines, consumed = _consume_table(lines, i)
            _validate_table(table_lines)
            stack[-1].body_lines.extend(table_lines)
            i += consumed
            continue

        # Everything else (paragraphs, HTML comments, lists, blank lines)
        # is preserved verbatim as body content of the currently open node.
        stack[-1].body_lines.append(line)
        i += 1

    if not saw_any_heading:
        raise EmptyDocumentError("Document contains no ATX headings; nothing to structure.")

    root.assign_logical_ids(prefix="")
    return root


def _consume_table(lines: list[str], start: int) -> tuple[list[str], int]:
    end = start
    while end < len(lines) and _TABLE_ROW_RE.match(lines[end]):
        end += 1
    return lines[start:end], end - start


def _validate_table(table_lines: list[str]) -> None:
    """Every row (including the separator) must have the same number of
    pipe-delimited columns as the header row. A mismatch means the table is
    malformed in a way this parser cannot safely interpret -> fail loud
    rather than silently misaligning columns."""
    if len(table_lines) < 2:
        raise MalformedTableError(f"Table block too short to be valid: {table_lines!r}")

    def col_count(row: str) -> int:
        return len([c for c in row.strip().strip("|").split("|")])

    header_cols = col_count(table_lines[0])
    for row in table_lines:
        if col_count(row) != header_cols:
            raise MalformedTableError(
                f"Inconsistent column count in table row (expected {header_cols}): {row!r}"
            )
