"""Dashboard endpoints — every path the frontend hits must return 200
with the shape the React mapper expects.
"""

from __future__ import annotations

import pytest


DASHBOARD_PATHS = [
    "/api/v1/dashboard/kpis",
    "/api/v1/dashboard/sla-status",
    "/api/v1/dashboard/category-distribution",
    "/api/v1/dashboard/department-load",
    "/api/v1/dashboard/recent-tickets",
    "/api/v1/dashboard/ai-metrics",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", DASHBOARD_PATHS)
async def test_dashboard_endpoints_return_200(client, auth_headers, path):
    r = await client.get(path, headers=auth_headers)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:300]}"
    body = r.json()
    assert body["success"] is True


@pytest.mark.asyncio
async def test_kpis_shape_has_required_fields(client, auth_headers):
    body = (await client.get("/api/v1/dashboard/kpis", headers=auth_headers)).json()["data"]
    required = {
        "total_open_tickets",
        "sla_breached_open",
        "resolved_today",
        "critical_high_open",
        "avg_resolution_hours_30d",
    }
    assert required.issubset(body.keys()), f"missing: {required - body.keys()}"


@pytest.mark.asyncio
async def test_category_distribution_shape(client, auth_headers):
    body = (
        await client.get(
            "/api/v1/dashboard/category-distribution", headers=auth_headers
        )
    ).json()["data"]
    assert "distribution" in body
    assert isinstance(body["distribution"], list)
    if body["distribution"]:
        row = body["distribution"][0]
        for k in ("category_id", "category_name", "ticket_count"):
            assert k in row, f"missing {k} in {row}"
