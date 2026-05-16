"""Sanity check that every API path the frontend's TypeScript hits really
exists on the backend. Greps the frontend source for ``api.<verb>(...)`` calls
and asserts each path maps to a route with the right method.

This catches the exact class of bug we hit before: a path/method drift between
frontend and backend that the type-checker can't see because requests are
strings.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
API_CALL_RE = re.compile(
    r"api\.(get|post|patch|put|delete)\(\s*[`'\"]([^`'\"]+)"
)


def _frontend_calls() -> list[tuple[str, str, Path]]:
    out: list[tuple[str, str, Path]] = []
    for path in FRONTEND_SRC.rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        for m in API_CALL_RE.finditer(text):
            verb, route = m.group(1).upper(), m.group(2)
            out.append((verb, route, path.relative_to(FRONTEND_SRC)))
    return out


def _backend_route_table() -> set[tuple[str, str]]:
    """Return (METHOD, regex-template) pairs for every API route in the app.

    Path parameters ``{name}`` become ``[^/]+`` so we can match the templates
    the frontend uses (which interpolate real ids).
    """
    from app.main import create_app

    app = create_app()
    table: set[tuple[str, str]] = set()
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        path = route.path  # e.g. /api/v1/tickets/{ticket_id}/status
        # The frontend baseURL strips /api/v1 (it's the axios baseURL).
        if path.startswith("/api/v1/"):
            path = path[len("/api/v1") :]
        regex = "^" + re.sub(r"\{[^}]+\}", r"[^/]+", path) + "$"
        for method in route.methods or set():
            table.add((method, regex))
    return table


def test_every_frontend_call_has_a_backend_route():
    table = _backend_route_table()
    failures: list[str] = []
    for verb, route, src in _frontend_calls():
        # Replace JS template-literal interpolations ${x} with a placeholder.
        normalised = re.sub(r"\$\{[^}]+\}", "PLACEHOLDER", route)
        matched_path = False
        matched_method = False
        for method, regex in table:
            if re.match(regex, normalised):
                matched_path = True
                if method == verb:
                    matched_method = True
                    break
        if not matched_path:
            failures.append(f"NO ROUTE  {verb} {route}   ({src})")
        elif not matched_method:
            failures.append(f"WRONG METHOD  {verb} {route}   ({src})")
    assert not failures, "Frontend↔backend drift:\n  " + "\n  ".join(failures)


def test_frontend_calls_were_actually_discovered():
    """Guard against the grep accidentally returning nothing (e.g. if the
    frontend tree moved). If this fails, the contract test above is silently
    passing on an empty set."""
    calls = _frontend_calls()
    assert len(calls) >= 15, f"Only found {len(calls)} api.* calls — regex may be broken"
