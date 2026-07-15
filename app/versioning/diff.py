"""Lightweight diff summaries for MODIFIED nodes, used by GET /node/{id}/changes
and the staleness endpoint.

Uses stdlib difflib line-level unified diff, truncated to a handful of
changed lines. This is intentionally simple: it tells a human *that* and
*roughly where* text changed, not a semantic classification of the change's
significance. See APPROACH.md "Known Limitations" — this cannot distinguish
a cosmetic wording fix from a safety-relevant threshold change (e.g. the
40mmHg -> 30mmHg increment change in CT-200 section 3.2), and we say so
explicitly rather than imply a smarter diff exists.
"""
import difflib

_MAX_DIFF_LINES = 12


def summarize_diff(old_text: str, new_text: str) -> str:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=0)
    )
    # Drop the '---'/'+++' header lines difflib always emits.
    diff_lines = [d for d in diff_lines if not d.startswith(("---", "+++"))]
    if not diff_lines:
        return "No textual difference detected."
    truncated = diff_lines[:_MAX_DIFF_LINES]
    summary = "\n".join(truncated)
    if len(diff_lines) > _MAX_DIFF_LINES:
        summary += f"\n... ({len(diff_lines) - _MAX_DIFF_LINES} more diff lines truncated)"
    return summary
