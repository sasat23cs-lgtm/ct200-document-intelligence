# CT-200 Document Intelligence API

A backend service that turns the CardioTrack CT-200 device manual into a
browsable, versioned document tree, lets users select sections and generate
QA test-case ideas via an LLM, and tracks whether those generated test cases
are still trustworthy as the source manual changes over time.

Built for the Tri9T AI Engineering Internship assignment.

## Overview

- **Parsing**: a purpose-built markdown parser turns the manual into a tree
  of nodes (heading, level, body, parent/children, content hash).
- **Versioning**: re-ingesting a modified manual creates a new version
  without destroying the old one; unchanged/modified/new/deleted nodes are
  detected via positional-path matching.
- **Selections**: users pin a named set of nodes from a specific version;
  that pin survives future re-ingestions.
- **LLM generation**: a selection's text is sent to an LLM to generate 3-5
  QA test cases, validated strictly against a Pydantic schema, with a
  retry-once-then-fail policy.
- **Staleness detection**: at retrieval time, generated test cases are
  flagged CURRENT or STALE by comparing recorded content hashes against the
  latest version of the document.

See `APPROACH.md` for the full design rationale, trade-offs, and decision
log.

## Architecture

```
backend/
  app/
    api/            FastAPI routers (thin, no business logic)
    core/            config, logging, exception hierarchy
    database/        SQLAlchemy engine/session, table init
    models/          SQLAlchemy ORM models
    schemas/         Pydantic request/response models
    parser/          markdown -> tree (ParsedNode)
    versioning/      node matching (v1<->v2) + diff summaries
    selection/        selection creation/resolution
    llm/             prompt templates, provider client, output validation, JSON store
    retrieval/       staleness computation
    services/        orchestration used by routers (ingestion, browse, generation, retrieval)
    utils/           hashing, text normalization
  tests/             pytest suite
  data/              ct200_manual.md, ct200_manual_v2.md, generations/ (JSON store)
  scripts/demo.py    scripted walkthrough of the versioning + staleness flow
```

Routers -> services -> (parser / versioning / selection / llm / retrieval).
ORM models never cross the API boundary directly; Pydantic schemas do.

## Tech stack

- FastAPI + Pydantic v2
- SQLAlchemy 2.0 + SQLite for documents, versions, nodes, selections
- A **JSON-file store** (not MongoDB) for LLM-generated output — see
  APPROACH.md "Database Design" for why this substitution is justified
- Any OpenAI-chat-completions-compatible LLM provider (Groq by default;
  OpenRouter/OpenAI work by changing env vars only)

## Installation

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Setup

```bash
cp .env.example .env
```

Edit `.env` if you want real LLM generation to work:

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./app.db` |
| `LLM_PROVIDER` | Informational only | `groq` |
| `LLM_API_KEY` | Your provider API key | *(none — generation returns a clear 502 without it)* |
| `LLM_MODEL` | Model name | `llama-3.3-70b-versatile` |
| `LLM_BASE_URL` | OpenAI-compatible base URL | `https://api.groq.com/openai/v1` |
| `LLM_TIMEOUT_SECONDS` | Request timeout | `30` |
| `LOG_LEVEL` | stdlib logging level | `INFO` |

Everything except LLM generation works with zero configuration.

## Running

```bash
uvicorn app.main:app --reload
```

- API base: `http://localhost:8000/api/v1`
- Interactive OpenAPI docs: `http://localhost:8000/docs`
- The database schema is created automatically on startup (`app.db`, an
  ordinary SQLite file in the `backend/` directory).

## API documentation

Full interactive docs (request/response schemas, try-it-out) are at
`/docs` once the server is running. Summary of routes:

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/documents/ingest` | Parse markdown, create a new document version |
| GET | `/api/v1/documents` | List documents (with their versions) |
| GET | `/api/v1/versions?document_id=` | List versions |
| GET | `/api/v1/sections?version_id=` | Top-level sections (defaults to latest version) |
| GET | `/api/v1/node/{id}` | Node detail: body, children, content hash |
| GET | `/api/v1/node/{id}/changes` | Whether/how this node changed vs. the previous version |
| GET | `/api/v1/search?q=&scope=` | Search headings/body/both |
| POST | `/api/v1/selections` | Create a version-pinned named selection |
| GET | `/api/v1/selections/{id}` | Fetch a selection |
| POST | `/api/v1/selections/{id}/generate` | Generate QA test cases via LLM |
| GET | `/api/v1/testcases/{selection_id}` | Retrieve generations for a selection, with staleness |
| GET | `/api/v1/testcases/node/{node_id}` | Retrieve generations touching a node, with staleness |

## Example requests

```bash
# Ingest v1
curl -X POST localhost:8000/api/v1/documents/ingest \
  -H "Content-Type: application/json" \
  -d "{\"document_name\": \"CT-200 Manual\", \"source_filename\": \"ct200_manual.md\", \"markdown_text\": $(python3 -c 'import json;print(json.dumps(open("data/ct200_manual.md").read()))')}"

# Search
curl "localhost:8000/api/v1/search?q=overpressure"

# Create a selection (node_ids from the search/sections response)
curl -X POST localhost:8000/api/v1/selections \
  -H "Content-Type: application/json" \
  -d '{"name": "Overpressure QA", "node_ids": [16]}'

# Generate test cases (requires LLM_API_KEY)
curl -X POST localhost:8000/api/v1/selections/1/generate

# Retrieve with staleness
curl localhost:8000/api/v1/testcases/1
```

## Version re-ingestion flow (v1 -> v2)

This is the core flow the assignment asks to see demonstrated end-to-end.

1. **Ingest v1**: `POST /api/v1/documents/ingest` with `ct200_manual.md`.
   Creates `DocumentVersion` #1 and its node tree.
2. **Create a selection** against a v1 node (e.g. the battery-life section)
   via `POST /api/v1/selections`.
3. **Generate test cases** for that selection via
   `POST /api/v1/selections/{id}/generate` (requires `LLM_API_KEY`).
4. **Re-ingest v2**: `POST /api/v1/documents/ingest` again with
   `ct200_manual_v2.md` and the **same** `document_name`. This creates
   `DocumentVersion` #2, leaves version 1's rows untouched, and computes a
   `NodeChange` diff between the two versions.
5. **Confirm version pinning**: `GET /api/v1/selections/{id}` and
   `GET /api/v1/node/{id}` still return the original v1 node — its text has
   not changed, because the selection points at the v1-specific node row.
6. **Check the diff directly**: `GET /api/v1/node/{id}/changes` on the v1
   node shows nothing (nothing to compare it *to* — it's the newest thing
   at the time it was created); the equivalent v2 node's `/changes` shows
   `MODIFIED` with a diff summary.
7. **Check staleness**: `GET /api/v1/testcases/{selection_id}` now reports
   `staleness_status: STALE`, with a per-node reason (`CONTENT_CHANGED`),
   old/new hash, and a diff summary — because the battery-life node's text
   changed between v1 and v2.

Run the whole thing scripted:

```bash
uvicorn app.main:app --reload &
python scripts/demo.py
```

(Steps involving actual LLM generation are skipped gracefully with a clear
message if `LLM_API_KEY` isn't set — everything else in the flow, including
version pinning and the node-level diff, works without it.)

## Testing

```bash
pytest -q
```

35 tests across:

- `tests/test_parser.py` (10) — duplicate headings, heading-depth-vs-label
  mismatch, out-of-order headings, tables, HTML comments, malformed-table
  failure, ordered lists, positional logical IDs.
- `tests/test_versioning.py` (6) — matcher unit tests (new/modified/deleted/
  unchanged, including a **synthetic** deletion case since the real CT-200
  data never deletes a node) + full ingestion/diff integration against the
  real v1/v2 files.
- `tests/test_selection.py` (3) — version pinning survives re-ingestion,
  cross-version selections are rejected, text reconstruction.
- `tests/test_llm_validation.py` (11) — schema validation (valid, malformed
  JSON, wrong count, missing field, lenient string-to-list coercion),
  retry-once-then-fail policy, duplicate-submission behavior.
- `tests/test_staleness.py` (5) — CURRENT when unchanged, STALE with correct
  reason/diff after a source edit, CURRENT for an untouched node after
  re-ingestion, cross-version node-id lookup, synthetic SOURCE_DELETED case.

## Project structure

See `Architecture` above; folder-by-folder responsibility is documented in
each module's docstring.
