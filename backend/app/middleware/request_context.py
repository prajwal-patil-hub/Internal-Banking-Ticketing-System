"""Request-scoped context: correlation ID, client IP, user agent.

Bound into structlog contextvars so every log line in this request carries
the same `request_id`. The ID is also written into the response header
`X-Request-ID` for cross-system tracing.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")

        request.state.request_id = request_id
        request.state.client_ip = client_ip
        request.state.user_agent = user_agent

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            client_ip=client_ip,
            method=request.method,
            path=request.url.path,
        )

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
