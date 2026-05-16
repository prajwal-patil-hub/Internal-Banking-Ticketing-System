"""Tickets lifecycle — exercises the enum round-trip fix (commit 2d8584a)
and the pagination envelope shape the frontend consumes.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_create_then_list_ticket(client, auth_headers):
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={
            "title": "Payment failure on UPI",
            "description": "User reports IMPS timeout for txn 1234",
            "priority": "high",
            "department": "Payments",
        },
    )
    assert create.status_code == 201, create.text
    created = create.json()["data"]
    assert created["status"] == "new"             # round-tripped lowercase enum value
    assert created["priority"] == "high"
    assert created["ticket_number"].startswith("TKT-")

    listing = await client.get("/api/v1/tickets?page=1&per_page=20", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    body = listing.json()
    # Envelope contract the frontend depends on
    assert body["success"] is True
    assert isinstance(body["data"], list)
    pagination = body["meta"]["pagination"]
    assert pagination["total"] >= 1
    assert pagination["page"] == 1
    assert pagination["size"] == 20
    assert pagination["pages"] >= 1
    titles = [t["title"] for t in body["data"]]
    assert "Payment failure on UPI" in titles


@pytest.mark.asyncio
async def test_status_transition_persists(client, auth_headers):
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Status round-trip", "priority": "medium"},
    )
    tid = create.json()["data"]["id"]

    transition = await client.post(
        f"/api/v1/tickets/{tid}/status",
        headers=auth_headers,
        json={"status": "in_progress", "reason": "picked up"},
    )
    assert transition.status_code == 200, transition.text
    assert transition.json()["data"]["status"] == "in_progress"

    detail = await client.get(f"/api/v1/tickets/{tid}", headers=auth_headers)
    assert detail.json()["data"]["status"] == "in_progress"
    assert detail.json()["data"]["first_response_at"] is not None


@pytest.mark.asyncio
async def test_list_pagination_filters(client, auth_headers):
    for i in range(3):
        await client.post(
            "/api/v1/tickets",
            headers=auth_headers,
            json={"title": f"Filter test {i}", "priority": "low"},
        )

    r = await client.get(
        "/api/v1/tickets?page=1&per_page=2&priority=low",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert all(t["priority"] == "low" for t in body["data"])
    assert body["meta"]["pagination"]["size"] == 2
