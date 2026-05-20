"""Regression: agents must be able to post AND see internal comments
on a ticket regardless of whether the ticket has an assignee.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_agent_posts_and_sees_internal_comment_on_unassigned_ticket(client, auth_headers):
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Unassigned ticket", "priority": "medium"},
    )
    tid = create.json()["data"]["id"]
    # ticket is intentionally NOT assigned to anyone

    # Agent posts an internal comment.
    post = await client.post(
        f"/api/v1/tickets/{tid}/comments",
        headers=auth_headers,
        json={"body": "Internal triage note", "is_internal": True},
    )
    assert post.status_code == 201, post.text
    assert post.json()["data"]["is_internal"] is True

    # Default listing excludes internal — frontend has to opt in via include_internal=true.
    public = await client.get(f"/api/v1/tickets/{tid}/comments", headers=auth_headers)
    assert all(c["is_internal"] is False for c in public.json()["data"])

    # Agent requesting include_internal=true sees the internal note they just posted.
    full = await client.get(
        f"/api/v1/tickets/{tid}/comments?include_internal=true",
        headers=auth_headers,
    )
    bodies = [c["body"] for c in full.json()["data"]]
    assert "Internal triage note" in bodies
