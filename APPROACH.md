# APPROACH.md

## 1. Architecture

Layered, single-service FastAPI app. Routers (`app/api/`) are thin — they
parse/validate the HTTP request via Pydantic, call a service function, and
return it. All business logic lives in `app/services/` (orchestration) and
domain packages (`parser/`, `versioning/`, `selection/`, `llm/`,
`retrieval/`). ORM models (`app/models/`) never cross the API boundary
directly — Pydantic schemas (`app/schemas/`) do. This separation is what
let every domain package be unit-tested without FastAPI or a real database
in the loop (the parser tests, for instance, import nothing from `api/` or
`database/` at all).

Two storage backends, matching the assignment's split of concerns:
- **SQLAlchemy + SQLite** for documents, versions, nodes, node changes,
  selections — structured, relational, needs joins and foreign keys.
- **JSON-file store** for LLM generation output — see "Database Design"
  below for why this replaces MongoDB.

## 2. Document analysis process (what I found, and how)

Before writing the parser I read both manuals fully, then confirmed my
reading with `diff -u ct200_manual.md ct200_manual_v2.md` and
`grep -n "^#"` to get a clean list of every heading with its depth. That
surfaced two things a straight read didn't make obvious at a glance:

1. **Depth vs. label mismatch**: `#### 2.1.1.1 Battery Life...` is one
   `#`-level below `### 2.1 General Specifications` (H4 under H3), but its
   numeric label (`2.1.1.1`) implies two levels of nesting under `2.1`. If
   a parser inferred structure from the numeric label instead of the actual
   `#` count, it would build a *different, wrong* tree that still looks
   plausible — exactly the "clean-looking but silently wrong" failure mode
   the assignment warns about.
2. **Out-of-order siblings**: `#### 3.2 Cuff Inflation Sequence` (H4,
   nested under 3.1) is followed by `### 3.4 Auto Shutoff` (H3) and *then*
   `### 3.3 Result Display and Classification` (H3) — 3.4 physically
   precedes 3.3 in the file. A parser that sorts children by parsing the
   numeric label would silently reorder them; one that trusts document
   position would not.

I confirmed both by writing a throwaway script that printed
`(logical_id, level, heading)` for every node and eyeballing the output
against the raw file line-by-line, before writing a single parser test.
Only after seeing the tree looked structurally correct did I write
`tests/test_parser.py` to lock the behavior in (`TestHeadingDepthVsLabelMismatch`,
`TestOutOfOrderHeadings`).

Other things found and how each is handled (also covered in `README.md`'s
architecture section and inline module docstrings):

| Finding | How found | Handling |
|---|---|---|
| Duplicate heading text ("Error Codes" at 4.2 and 7.1) | `grep -n "^### "` showed two identical strings | Node identity is never derived from heading text; positional path (`logical_node_id`) and DB parent_id disambiguate them |
| HTML comment before any heading | Read raw file | Attached to the root/H1 node's body, not dropped |
| GFM tables (2.1, 4.2) | Read raw file | Preserved verbatim in `body`; column-count mismatch across rows fails loudly (`MalformedTableError`) rather than misaligning |
| Ordered list embedded in prose (3.3) | Read raw file | Kept as part of the owning node's body, not split into child nodes — the assignment's node model (heading/level/body/children) treats a list as content, not structure |
| Heading with own body *and* child headings (Section 1) | Read raw file | Node's `body` and `children` are independent fields; not mutually exclusive |
| Unicode non-breaking hyphens (`user‑configurable`, U+2011) | Manual copy-paste inspection | Normalized only for the search index (`normalize_for_search`), never for hashing/display, so hashing stays byte-faithful |
| "Anthropic recommends..." in 6.2 (likely a copy-paste artifact, should probably read "CardioTrack") | Read raw file | Left exactly as authored — not the parser's job to correct source content, and the assignment says not to invent/alter data |
| v1→v2 diff has **zero deletions** | `diff -u` | `tests/test_versioning.py::TestMatchVersionsUnit::test_deleted_node_detected_synthetic_case` and `tests/test_staleness.py::test_staleness_reports_source_deleted_for_synthetic_case` use synthetic fixtures, since the real data never exercises this path |

## 3. Parser design

Single-pass, line-based, purpose-built for this document family (explicitly
not a general CommonMark parser, per the assignment's "explicitly out of
scope"). A stack tracks currently-open headings by depth; a new heading's
parent is the nearest still-open heading with a strictly smaller `#` count.
This is what makes both irregularities above resolve correctly without any
special-casing: heading depth is the *only* signal used for structure,
never the numeric label, and children are appended in document order, never
re-sorted.

Everything that isn't a heading (paragraphs, HTML comments, table rows,
list items, blank lines) is appended verbatim to the currently open node's
body buffer — nothing is normalized or reformatted before storage, so
`content_hash` is computed over text as close to the original as reasonably
possible (only trailing-whitespace/line-ending noise is stripped, deliberately,
to avoid hash instability from formatting that carries no information).

**Fail-loud cases**: a table block where rows have inconsistent
pipe-delimited column counts raises `MalformedTableError`; a document with
no headings at all raises `EmptyDocumentError`. I chose these two because
they're the only "I genuinely cannot know what you meant" cases in this
document family — everything else (depth/label mismatch, out-of-order
labels, duplicate headings) has one defensible, deterministic
interpretation once you commit to "trust markdown depth and document
order," so those don't need to fail; they need to be handled predictably
and documented, which is what the parser does.

## 4. Database design

**Documents / DocumentVersions / Nodes / NodeChanges / Selections /
SelectionNodes** — see `app/models/*.py` docstrings for field-level
rationale. Two decisions worth calling out:

- `DocumentVersion` rows are **never mutated or deleted** after creation.
  This single invariant is what makes version-pinned selections actually
  work: a `SelectionNode.node_id` foreign key points at a specific,
  permanent `Node` row, not at a `(document_id, version_number)` pair that
  could be reinterpreted later.
- `NodeChange` only persists NEW/MODIFIED/DELETED rows, not UNCHANGED. For
  this document (~35 nodes) it wouldn't matter, but persisting an UNCHANGED
  row for every untouched node on every re-ingest is an unnecessary O(n)
  write for information you can derive for free ("no NodeChange row for
  this logical_node_id at this version = unchanged").

**MongoDB → JSON-file store, justified**: the assignment allows a
"well-justified JSON store" as a substitute. I chose one because (a) a
take-home reviewer shouldn't need a MongoDB instance running to evaluate
this, (b) generation records are small, read-mostly, single-writer, and
don't need cross-document transactions, joins, or complex queries — the
things Mongo is actually good at — and (c) the access pattern is fully
isolated behind `GenerationRepository` (`app/llm/repository.py`), so
swapping in real MongoDB later is a one-file change, not a redesign.
**Known limitation, stated plainly**: this JSON store has no file locking,
so it is not safe for concurrent multi-process writers. Fine for a
single-process dev/demo API; would need to change before any real
production use with multiple workers.

## 5. Version matching strategy

**Chosen: positional-path matching.** Every node gets a `logical_node_id`
that is the sequence of sibling-order indices from the root
(e.g. `0.3.1`), computed identically by the parser on every ingestion. Two
nodes across versions are "the same logical node" iff they share this path.

**Why not the alternatives:**
- *Hash-based matching* (same content_hash = same node): fails on exactly
  the case we most need — a node whose text changed would be reported as
  "deleted + new" instead of "modified," which is the opposite of useful
  for staleness detection.
- *Heading-text matching*: fails on this exact document, since "Error
  Codes" appears twice (4.2 and 7.1) with different parents. Any fix to
  that ("match on heading + parent heading") is just positional matching
  with extra steps.

**Where positional matching breaks** (stated honestly, not hidden): if the
document is reordered, or a section is inserted/removed in the *middle* of
a sibling list, every sibling after the insertion point shifts its
`order_index`, and the matcher will misclassify unrelated, unchanged nodes
as modified/new/deleted. The real CT-200 v1→v2 diff never reorders
anything (confirmed via `diff -u` — it's pure text edits plus one
appended child at the end of section 5), so this fixture doesn't exercise
the failure mode, but it is a real, documented limitation of the approach,
not a hypothetical one.

## 6. Hashing strategy

`content_hash = sha256(heading + normalized_body)`. Including the heading
means a heading-only rename is still detected even if body text is
untouched. Normalization is deliberately minimal — only trailing
whitespace and line-ending differences are collapsed — so the hash is
sensitive to any change a human would consider a real edit, including
single-character changes (a threshold number, a word). This is also why
staleness detection is binary and coarse (see Section 8): the hash cannot
tell you *how much* changed, only *that* something did.

## 7. LLM strategy

**Prompt design** (`app/llm/prompts.py`): the model is told explicitly it's
writing QA test cases for a *regulated medical device*, to derive facts
*only* from the given excerpt (not invent thresholds/behavior), to return
*only* a JSON array (no prose, no code fences) matching an exact field
list, and to prioritize safety-relevant content (error codes, alarms,
overpressure) as High/Critical. Being explicit about "don't invent facts
outside this excerpt" matters more here than in a generic QA-generation
prompt, because a hallucinated threshold in a medical-device test case is a
much worse failure than a vague one.

**Provider**: any OpenAI-chat-completions-compatible endpoint
(`app/llm/client.py`). Groq is the default because it's free-tier and fast;
switching to OpenRouter/OpenAI is an env-var change (`LLM_BASE_URL`,
`LLM_MODEL`, `LLM_API_KEY`), not a code change.

## 8. Structured-output validation & retry strategy

Every response is parsed and validated against `TestCase` (Pydantic) before
being trusted — see `app/llm/validator.py`. Validation covers: valid JSON,
correct top-level shape (array, with a lenient allowance for a
`{"test_cases": [...]}` wrapper some models add despite instructions),
required fields present, and a test-case count strictly between 3 and 5.
One deliberate leniency: a `preconditions`/`test_steps` field returned as a
single string instead of an array is coerced to a one-item array rather
than rejected — this is a benign, common shape variance that costs nothing
to accept and doesn't compromise the actual content being validated.

**Retry policy**: on validation failure, retry exactly once, feeding the
validation error back into the prompt so the model can see what was wrong.
If the second attempt also fails validation, the failure (prompt, raw
response, error) is persisted with `status=FAILED` — never silently
dropped — and the API returns a 502 with a clear message including the
generation record's id, so the failure is inspectable later. "It usually
works" is explicitly not the design; every path is tested in
`tests/test_llm_validation.py` (`TestGenerationRetryPolicy`).

**Duplicate-submission policy**: resubmitting the same selection creates a
**new** generation record rather than overwriting the previous one.
Generations are append-only history. Rationale: a prior generation may
already be in use elsewhere (referenced by a user, exported, etc.), and
silently overwriting it is a worse failure mode than having two records —
retrieval returns all of them (most recent first), so nothing is hidden.

## 9. Staleness / impact detection

At retrieval time (`app/retrieval/staleness.py`), for every
`(logical_node_id, content_hash)` pair a generation was created from, the
system looks up the current node with that logical id in the document's
*latest* version and compares hashes:

- Hash matches → `CURRENT`.
- Hash differs → `STALE`, reason `CONTENT_CHANGED`, with old/new hash and a
  `difflib`-based unified-diff summary.
- No current node with that logical id exists → `STALE`, reason
  `SOURCE_DELETED`.

**Honesty about the limitation** (the assignment specifically asks for
this): hash comparison is binary. It **cannot** distinguish a one-word
wording fix from a safety-relevant change — the CT-200 v1→v2 diff includes
exactly this ambiguity: the inflation-increment change in section 3.2
(40mmHg → 30mmHg, a specification with real safety implications) produces
the *identical* STALE signal as a cosmetic typo fix would. The system's job
here is to flag "this needs human review," not to judge how urgently — a
smarter version might weight changes (e.g. changed numbers vs. changed
prose) differently, but that's explicitly not what's implemented, and I'd
rather say so than imply a semantic diff exists when it doesn't.

## 10. Testing strategy

35 tests, organized by concern (`tests/test_parser.py`,
`test_versioning.py`, `test_selection.py`, `test_llm_validation.py`,
`test_staleness.py`) — see README.md's Testing section for the full
breakdown. Two testing decisions worth noting:

- The parser tests run directly against the real `data/ct200_manual.md`
  file for the irregularity-specific tests (duplicate headings, depth/label
  mismatch, out-of-order headings) rather than synthetic fixtures, so a
  regression in real-document behavior is caught, not just a regression in
  a simplified example.
- Where the real data doesn't exercise a code path (node deletion), tests
  use a small synthetic fixture instead of skipping the case — a passing
  test suite should mean the deletion path actually works, not that it was
  never exercised.
- `LLMClient` is a `Protocol`, and generation-service tests inject a
  `FakeLLMClient` with scripted responses — no test in this suite makes a
  real network call, so the suite is fast and deterministic.

## 11. Known limitations

- Positional-path version matching breaks under document reordering (see
  Section 5).
- Staleness is a binary hash comparison with no severity weighting (Section 9).
- The JSON generation store has no concurrent-write safety (Section 4).
- The parser is intentionally not a general markdown parser — feeding it an
  arbitrary markdown file with structures outside what's described above
  (e.g. nested bullet lists, blockquotes, inline code spans containing
  pipe characters) is untested territory; it will either work by accident
  or raise a `ParserError`, and I haven't audited every such case, only the
  ones actually present in `ct200_manual.md`/`v2.md`.
- No auth, as explicitly scoped out.

## 12. Future improvements (with more time)

- A configurable "significance" signal for staleness — e.g. flag numeric
  changes (thresholds, ranges) as higher severity than prose-only edits, by
  diffing structured tokens rather than just comparing hashes.
- A real MongoDB-backed `GenerationRepository` implementation behind the
  same interface, for concurrent-safe multi-worker deployment.
- A reordering-tolerant version matcher (e.g. a two-pass match: exact path
  first, then a similarity fallback for unmatched nodes) to reduce false
  positives when sections move.
- Alembic migrations instead of `create_all()` for schema evolution.

## 13. Decision log

**1. What's the one part of this system most likely to silently give wrong
results without erroring? How would you catch it?**

The version matcher, specifically under document reordering. Positional-path
matching will happily produce a *complete, well-formed* diff (every path
classified as new/modified/deleted/unchanged) even when the underlying
document was reordered rather than edited — it will never raise an error,
it will just attribute changes to the wrong logical nodes. This is the
"clean-looking output that's quietly wrong" failure mode the assignment
warns about, and it's the one place in the system where I don't have a
mechanism that would catch it automatically. The way I'd catch it in
practice: an alarm on ingestion when the *set* of unchanged content hashes
between versions is much larger than the set of paths the matcher called
unchanged — a big gap there is a strong signal that content moved rather
than changed, and would be worth a manual review step before trusting the
diff.

**2. Where did you choose simplicity over correctness because of time, and
what would break first if this went to production as-is?**

The JSON-file generation store, and the fact that `content_hash` treats
every text change identically regardless of significance. In production,
the JSON store would break first — no file locking means concurrent
requests from multiple API workers can race on the counter file and on
individual generation files, and there's no transactional guarantee tying
a generation record to the SQL rows it references. The binary staleness
signal would be the second thing to bite: a compliance-focused user would
reasonably expect "STALE because a pressure threshold changed" to be
flagged differently from "STALE because of a typo fix," and right now
both look identical in the API response.

**3. Name one input you did not handle, and what your system does when it
sees it.**

A markdown table where a row contains a literal, unescaped `|` character
inside a cell's text (not a valid pipe-escape). My row-splitting logic
(`row.strip().strip("|").split("|")`) would count that as an extra column
and raise `MalformedTableError`, aborting ingestion of the whole document —
even though a smarter table parser could have handled it correctly. This
input doesn't appear in `ct200_manual.md`/`v2.md`, so it's untested and
unhandled by design (failing loudly rather than silently misaligning
columns), consistent with the parser's stated philosophy, but it is a real
gap: a legitimately well-formed manual using that character would be
rejected outright rather than parsed correctly.
