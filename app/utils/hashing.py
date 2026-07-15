"""Hashing and text-normalization helpers.

Two distinct normalization needs exist in this system and they must NOT be
conflated:

1. Content hashing (staleness detection) — must be byte-sensitive to any
   meaningful text change, so normalization here is minimal (just trailing
   whitespace / line-ending noise) to avoid hash instability from irrelevant
   formatting.
2. Search indexing — needs to be forgiving of Unicode hyphen variants etc.
   so a plain-ASCII query matches "low‑battery" (U+2011 non-breaking hyphen).
   This normalization is ONLY used for the search index, never for hashing
   or for display, so body text shown to users stays byte-faithful.
"""
import hashlib
import re
import unicodedata

# Characters that are visually/semantically hyphens but not ASCII '-'.
_HYPHEN_VARIANTS = {
    "\u2010",  # hyphen
    "\u2011",  # non-breaking hyphen
    "\u2012",  # figure dash
    "\u2013",  # en dash
    "\u2014",  # em dash
}


def compute_content_hash(heading: str, body: str) -> str:
    """Stable content hash for a node. Includes the heading so a heading-only
    rename is still detected as a change, even if body text is untouched."""
    normalized = f"{heading.strip()}\n{_normalize_whitespace(body)}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_whitespace(text: str) -> str:
    # Collapse trailing whitespace per line and normalize line endings only —
    # deliberately does NOT touch punctuation/hyphen characters, since those
    # are semantically meaningful for hashing purposes.
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip()


def normalize_for_search(text: str) -> str:
    """Lowercase, NFKC-normalize, and fold hyphen-variant characters to ASCII
    '-' so search is resilient to the Unicode punctuation found in the source
    manual (e.g. 'user‑configurable')."""
    text = unicodedata.normalize("NFKC", text).lower()
    for variant in _HYPHEN_VARIANTS:
        text = text.replace(variant, "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
