"""End-to-end demo of the versioning + staleness flow, against a running server.

Run the API first:
    uvicorn app.main:app --reload

Then, in another terminal:
    python scripts/demo.py

This mirrors exactly what the README's curl walkthrough does, but as a
single script so it's easy to eyeball the whole flow at once. It does NOT
require an LLM API key to demonstrate versioning/staleness — it only
attempts real generation if LLM_API_KEY is set, and explains what it's
doing either way.
"""
import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def step(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)
    print(client.base_url)

    step("1. Ingest CT-200 Manual v1")
    v1_text = (DATA_DIR / "ct200_manual.md").read_text()
    
    print("Base URL:", client.base_url)
    print("Calling:", str(client.base_url) + "documents/ingest")
    r = client.post(
        "/documents/ingest",
        json={"document_name": "CT-200 Manual", "source_filename": "ct200_manual.md", "markdown_text": v1_text},
    )
    r.raise_for_status()
    v1 = r.json()
    print(f"Created version {v1['version_number']} (id={v1['id']})")

    step("2. Browse top-level sections of v1")
    r = client.get("/sections", params={"version_id": v1["id"]})
    sections = r.json()
    for s in sections:
        print(f"  [{s['id']}] {s['heading']}")

    step("3. Search for the battery life node")
    r = client.get("/search", params={"q": "battery life", "version_id": v1["id"]})
    battery_node = r.json()[0]
    print(f"Found node {battery_node['id']}: {battery_node['heading']}")

    step("4. Create a version-pinned selection from that node")
    r = client.post("/selections", json={"name": "Battery life QA", "node_ids": [battery_node["id"]]})
    r.raise_for_status()
    selection = r.json()
    print(json.dumps(selection, indent=2))

    step("5. Generate QA test cases for the selection (LLM)")
    r = client.post(f"/selections/{selection['id']}/generate")
    if r.status_code == 201:
        generation = r.json()
        print(f"Generation id={generation['id']} status={generation['status']}")
        print(json.dumps(generation.get("test_cases"), indent=2))
    else:
        print(f"Generation call returned {r.status_code}: {r.json()}")
        print(
            "(This is expected if LLM_API_KEY isn't set in .env — the "
            "generation feature requires a real provider key. The rest of "
            "this demo continues without it.)"
        )

    step("6. Retrieve current staleness status (should be CURRENT — nothing re-ingested yet)")
    r = client.get(f"/testcases/{selection['id']}")
    print(json.dumps(r.json(), indent=2)[:1500])

    step("7. Re-ingest CT-200 Manual v2 (battery life section's text changed)")
    v2_text = (DATA_DIR / "ct200_manual_v2.md").read_text()
    r = client.post(
        "/documents/ingest",
        json={"document_name": "CT-200 Manual", "source_filename": "ct200_manual_v2.md", "markdown_text": v2_text},
    )

    print("Status:", r.status_code)
    ~print("Response:", r.text)
    r.raise_for_status()
    v2 = r.json()
    print(f"Created version {v2['version_number']} (id={v2['id']})")

    step("8. Confirm the ORIGINAL selection still resolves to v1 text (version pinning)")
    r = client.get(f"/selections/{selection['id']}")
    print(json.dumps(r.json(), indent=2))
    r = client.get(f"/node/{battery_node['id']}")
    node_detail = r.json()
    assert "300 measurement cycles" in node_detail["body"], "selection should still show v1 text"
    print("Confirmed: selection's node body still shows v1's '300 measurement cycles' text.")

    step("9. Check node-level diff for the battery node (GET /node/{id}/changes)")
    r = client.get(f"/node/{battery_node['id']}/changes")
    print(json.dumps(r.json(), indent=2))

    step("10. Retrieve staleness again — should now be STALE")
    r = client.get(f"/testcases/{selection['id']}")
    print(json.dumps(r.json(), indent=2)[:2000])

    step("11. Query staleness by node id instead of selection id")
    r = client.get("/search", params={"q": "battery life", "version_id": v2["id"]})
    battery_node_v2 = r.json()[0]
    r = client.get(f"/testcases/node/{battery_node_v2['id']}")
    print(json.dumps(r.json(), indent=2)[:2000])

    print("\nDemo complete.")


if __name__ == "__main__":
    try:
        main()
    except httpx.ConnectError:
        print("Could not connect to http://localhost:8000 — start the API first with:")
        print("    uvicorn app.main:app --reload")
        sys.exit(1)
