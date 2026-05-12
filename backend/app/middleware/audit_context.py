"""Per-request audit context made available to services without dragging
the FastAPI Request through every call site.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_audit_ctx: ContextVar[dict[str, Any]] = ContextVar("audit_ctx", default={})


def current_audit_context() -> dict[str, Any]:
    return _audit_ctx.get()


class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = _audit_ctx.set(
            {
                "ip": getattr(request.state, "client_ip", ""),
                "user_agent": getattr(request.state, "user_agent", ""),
                "request_id": getattr(request.state, "request_id", ""),
            }
        )
        try:
            response: Response = await call_next(request)
            return response
        finally:
            _audit_ctx.reset(token)
