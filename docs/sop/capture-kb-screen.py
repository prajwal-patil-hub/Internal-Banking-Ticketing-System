"""Capture the Knowledge Base screen for the SOP deck.

The deck's standing rule is that a slide never shows a screenshot of a screen
nobody actually opened. This script honours that while working around the fact
that a knowledge-base answer needs Postgres with pgvector, MinIO and a local
embedding model — none of which exist in a documentation build.

So it renders **the real page component** from the real bundle, with the
`/api/v1/kb/*` responses intercepted and served from fixtures. Everything on
the resulting image — layout, spacing, pill colours, the empty and error
states — is produced by `KnowledgeBasePage.tsx` itself. Only the rows are
fixtures, and they are shaped exactly like the serializers in
`app/api/v1/routes/knowledge.py` produce, so a drift in the API contract shows
up here as a broken screenshot rather than a pretty lie.

    python docs/sop/capture-kb-screen.py <out-dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from capture_config import DEVICE_SCALE_FACTOR, VIEWPORT

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/sop/screens")
OUT.mkdir(parents=True, exist_ok=True)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
PORT = 5251
BASE = f"http://127.0.0.1:{PORT}"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

USER = {
    "id": "11111111-1111-1111-1111-111111111111",
    "email": "priya.nair@successbank.local",
    "full_name": "Priya Nair",
    "role": "admin",
    "branch_id": None,
    "mfa_enabled": True,
    "org_unit_id": None,
    "org_unit": None,
    "org_role_id": None,
    "org_role": None,
    "is_super_admin": False,
}

COLLECTIONS = [
    {
        "id": "c1",
        "name": "Compliance policies",
        "description": "KYC, AML and regulatory circulars.",
        "is_active": True,
        "granted_roles": ["admin", "agent", "supervisor"],
        "document_count": 12,
        "created_at": "2026-06-02T09:00:00Z",
    },
    {
        "id": "c2",
        "name": "Disputes & chargebacks",
        "description": "Scheme rules, timelines and evidence templates.",
        "is_active": True,
        "granted_roles": ["admin", "agent"],
        "document_count": 7,
        "created_at": "2026-06-11T09:00:00Z",
    },
    {
        "id": "c3",
        "name": "Treasury runbooks",
        # Deliberately ungranted: the screenshot has to show the warning state,
        # because "uploaded but searchable by nobody" is the mistake this
        # screen exists to make visible.
        "granted_roles": [],
        "description": "Settlement and reconciliation procedure.",
        "is_active": True,
        "document_count": 3,
        "created_at": "2026-07-01T09:00:00Z",
    },
]

DOCUMENTS = [
    {
        "id": "d1",
        "collection_id": "c2",
        "title": "Chargeback Handling Policy v4",
        "original_filename": "chargeback-policy-v4.pdf",
        "content_type": "application/pdf",
        "status": "ready",
        "chunk_count": 184,
        "page_count": 42,
        "size_bytes": 2_310_000,
        "active_version_no": 4,
        "version_count": 4,
        "versions": [],
        "created_at": "2026-07-14T10:00:00Z",
        "updated_at": "2026-08-02T10:00:00Z",
    },
    {
        "id": "d2",
        "collection_id": "c2",
        "title": "Scheme Timelines Matrix",
        "original_filename": "scheme-timelines.xlsx.docx",
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "status": "processing",
        "chunk_count": 0,
        "page_count": None,
        "size_bytes": 486_000,
        "active_version_no": None,
        "version_count": 1,
        "versions": [],
        "created_at": "2026-08-26T14:20:00Z",
        "updated_at": "2026-08-26T14:20:00Z",
    },
    {
        "id": "d3",
        "collection_id": "c2",
        "title": "Evidence Pack Template",
        "original_filename": "evidence-pack.pdf",
        "content_type": "application/pdf",
        "status": "failed",
        "chunk_count": 0,
        "page_count": None,
        "size_bytes": 1_120_000,
        "active_version_no": None,
        "version_count": 1,
        "versions": [
            {
                "id": "v3",
                "version_no": 1,
                "status": "failed",
                "error_message": (
                    "No text could be extracted from this PDF — it appears to be a "
                    "scanned image. OCR is not enabled, so upload a text-based PDF."
                ),
                "chunk_count": 0,
                "embedded_count": 0,
                "page_count": None,
                "size_bytes": 1_120_000,
                "embedding_model": "nomic-embed-text",
                "is_active": False,
                "created_at": "2026-08-26T15:00:00Z",
            }
        ],
        "created_at": "2026-08-26T15:00:00Z",
        "updated_at": "2026-08-26T15:00:00Z",
    },
]

STATUS = {
    "enabled": True,
    "embedding_model": "nomic-embed-text",
    "embedding_dim": 768,
    "accessible_collections": 3,
    "indexed_chunks": 1_463,
    "versions_in_progress": 1,
    "versions_failed": 1,
    "can_manage": True,
}

ANSWER = {
    "question": "How long does a customer have to raise a chargeback?",
    "answer": (
        "A service dispute must be raised within 45 days of the transaction "
        "date [1]. Fraud claims run to a longer 120-day window and are owned "
        "by Fraud Ops rather than Disputes [2]."
    ),
    "abstained": False,
    "abstain_reason": None,
    "confidence": 0.87,
    "confidence_band": "high",
    "sources": [
        {
            "chunk_id": "k1",
            "document_id": "d1",
            "document_title": "Chargeback Handling Policy v4",
            "heading_path": "3. Chargebacks > 3.2 Timelines",
            "page_from": 11,
            "page_to": 11,
            "similarity": 0.91,
            "cited": True,
            "marker": 1,
            "excerpt": (
                "A chargeback must be raised within 45 days of the transaction "
                "date. Late claims are rejected automatically by the scheme."
            ),
        },
        {
            "chunk_id": "k2",
            "document_id": "d1",
            "document_title": "Chargeback Handling Policy v4",
            "heading_path": "3. Chargebacks > 3.4 Fraud claims",
            "page_from": 14,
            "page_to": 14,
            "similarity": 0.84,
            "cited": True,
            "marker": 2,
            "excerpt": (
                "Fraud | 120 days | Fraud Ops. Service | 45 days | Disputes."
            ),
        },
        {
            "chunk_id": "k3",
            "document_id": "d1",
            "document_title": "Chargeback Handling Policy v4",
            "heading_path": "3. Chargebacks > 3.3 Evidence",
            "page_from": 12,
            "page_to": 12,
            "similarity": 0.62,
            "cited": False,
            "marker": 3,
            "excerpt": "Attach the signed dispute form and the statement extract.",
        },
    ],
    "rejected_citations": [],
    "error": None,
    "timing": {"retrieval_ms": 41, "total_ms": 2380},
}


def envelope(data):
    return {"success": True, "data": data, "meta": {}, "error": None}


def main() -> int:
    print("building the frontend…")
    subprocess.run(["npx", "vite", "build"], cwd=FRONTEND, check=True,
                   stdout=subprocess.DEVNULL)

    server = subprocess.Popen(
        ["npx", "vite", "preview", "--port", str(PORT), "--strictPort"],
        cwd=FRONTEND, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(4)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=CHROME, args=["--no-sandbox"]
            )
            page = browser.new_page(viewport=VIEWPORT,
                                    device_scale_factor=DEVICE_SCALE_FACTOR)

            def route(pattern, payload):
                page.route(
                    pattern,
                    lambda r: r.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(envelope(payload)),
                    ),
                )

            # Playwright gives precedence to the *last* registered matching
            # route, so the catch-all has to go first or it shadows every
            # specific fixture below it and the page renders empty.
            page.route("**/api/v1/**", lambda r: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(envelope([])),
            ))
            route("**/api/v1/kb/status", STATUS)
            route("**/api/v1/kb/collections", COLLECTIONS)
            route("**/api/v1/kb/collections/*/documents", DOCUMENTS)
            route("**/api/v1/kb/query", ANSWER)

            page.goto(f"{BASE}/login", wait_until="domcontentloaded")
            page.evaluate(
                """([user]) => {
                    localStorage.setItem('access_token', 'sop-capture');
                    localStorage.setItem('success-auth', JSON.stringify({
                        state: { user, accessToken: 'sop-capture',
                                 refreshToken: 'sop-capture' },
                        version: 0,
                    }));
                }""",
                [USER],
            )

            page.goto(f"{BASE}/knowledge", wait_until="networkidle")
            page.wait_for_selector("text=Knowledge Base", timeout=15000)

            # Select the collection whose documents show all three states.
            # Located by its text rather than by role name: the button wraps
            # the name, the document count and the "not searchable" warning,
            # so its accessible name is the concatenation of all three.
            page.get_by_text("Disputes & chargebacks", exact=True).click()
            page.wait_for_timeout(400)

            # Run a question so the answer panel, citations and the
            # retrieved-but-not-cited distinction are all on the image.
            page.get_by_label("Your question for the knowledge base").fill(
                ANSWER["question"]
            )
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_selector("text=Cited sources", timeout=15000)
            page.wait_for_timeout(500)

            # The skeletons must be gone or the shot records a loading state.
            page.wait_for_function(
                "() => document.querySelectorAll('.animate-pulse').length === 0",
                timeout=15000,
            )

            # The floating chat launcher is fixed to the viewport, so on a
            # full-page capture it lands in the middle of the document list and
            # reads as a stray artefact on the slide. It belongs to a different
            # feature; hide it rather than crop around it.
            page.evaluate(
                """() => {
                    const b = document.querySelector('[aria-label="Open AI Assistant"]');
                    if (b) b.style.display = 'none';
                }"""
            )
            page.wait_for_timeout(150)

            shots = {}

            def grab(key, filename, callouts):
                """Screenshot plus the on-screen position of each callout target.

                Positions are measured from the live DOM rather than guessed as
                percentages — the first version of this deck guessed, and put
                markers beside controls instead of on them.
                """
                page.wait_for_timeout(250)
                # Viewport capture, not full page. Every other screen in the
                # deck is a 1440x900 viewport shot; a full-page capture of this
                # long screen comes out near-square and overflows the slide.
                box = page.evaluate("() => ({w: innerWidth, h: innerHeight})")
                recorded = []
                for label, selector in callouts:
                    loc = page.locator(selector).first
                    if loc.count() == 0:
                        print(f"  ! {key}: no match for {selector!r} — callout dropped")
                        continue
                    # getBoundingClientRect is viewport-relative, which is what
                    # the fractions must be measured against now that the
                    # screenshot is the viewport rather than the document.
                    r = loc.evaluate(
                        "el => { const b = el.getBoundingClientRect();"
                        " return {x: b.x, y: b.y, width: b.width, height: b.height}; }"
                    )
                    if r["y"] < 0 or r["y"] + r["height"] > box["h"]:
                        print(f"  ! {key}: {selector!r} outside the viewport — callout dropped")
                        continue
                    recorded.append({
                        "label": label,
                        "x0": round(r["x"] / box["w"], 4),
                        "y0": round(r["y"] / box["h"], 4),
                        "w": round(r["width"] / box["w"], 4),
                        "h": round(r["height"] / box["h"], 4),
                        "x": round((r["x"] + r["width"] / 2) / box["w"], 4),
                        "y": round((r["y"] + r["height"] / 2) / box["h"], 4),
                    })
                page.screenshot(path=str(OUT / filename))
                shots[key] = {"file": filename, "callouts": recorded}
                print(f"saved {OUT / filename} ({len(recorded)} callouts)")

            page.evaluate("() => scrollTo(0, 0)")
            page.wait_for_timeout(250)
            grab("70-kb-answer", "70-kb-answer.png", [
                ("Ask in plain words — no query syntax", "input[aria-label='Your question for the knowledge base']"),
                ("Confidence, computed from the evidence", "text=High confidence"),
                ("Cited sources: document, section, page", "text=CITED SOURCES"),
                ("Also retrieved but not cited", "text=ALSO RETRIEVED, NOT CITED"),
            ])

            # Curation half: scroll so the collection and document cards are in view.
            page.get_by_text("Documents", exact=True).first.scroll_into_view_if_needed()
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(400)
            grab("71-kb-documents", "71-kb-documents.png", [
                ("Upload PDF, Word, Markdown, text or CSV", "button:has-text('Upload document')"),
                ("Which roles may search this collection", "text=WHO CAN SEARCH THIS COLLECTION"),
                ("A collection nobody can read is flagged", "text=No roles granted"),
                ("A document that failed says why", "text=scanned image"),
            ])

            # An answer the system declined to give.
            page.get_by_label("Your question for the knowledge base").fill(
                "What is the staff car parking policy?")
            page.route("**/api/v1/kb/query", lambda r: r.fulfill(
                status=200, content_type="application/json",
                body=json.dumps(envelope({**ANSWER, "answer": None, "abstained": True,
                                          "abstain_reason": "no_passages", "confidence": 0.0,
                                          "confidence_band": "low", "sources": []}))))
            page.get_by_role("button", name="Ask", exact=True).click()
            page.wait_for_selector("text=No grounded answer", timeout=15000)
            page.evaluate("() => scrollTo(0, 0)")
            page.wait_for_timeout(400)
            grab("72-kb-abstain", "72-kb-abstain.png", [
                ("It says so and stops, rather than guessing",
                 "text=No grounded answer"),
            ])

            # Merge into the deck manifest so build-deck.py can use these.
            manifest_path = OUT / "manifest.json"
            manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
            manifest.update(shots)
            manifest_path.write_text(json.dumps(manifest, indent=2))
            print(f"manifest updated: {len(shots)} knowledge-base screens")

            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
