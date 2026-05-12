"""HTTP rate-limit middleware.

Two policies are applied:
  - LOGIN_LIMIT  : 10 requests / minute / IP on POST /auth/login (credential-stuffing defense)
  - WRITE_LIMIT  : 120 writes  / minute / actor (auth) or IP (anon)
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.rate_limit import check

LOGIN_LIMIT = (10, 60)            # (requests, seconds)
WRITE_LIMIT = (120, 60)
EXEMPT_PREFIXES = ("/api/v1/healthz", "/api/v1/readyz", "/api/docs", "/api/openapi.json", "/metrics")


def _exempt(path: str) -> bool:
    return any(path.startswith(p) for p in EXEMPT_PREFIXES)


def _too_many(reset: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "data": None,
            "error": {
                "code": "RATE_LIMITED",
                "message": "Too many requests.",
                "details": {"retry_after_seconds": reset},
            },
            "request_id": None,
        },
        headers={"Retry-After": str(reset)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _exempt(path):
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"

        # 1. Login is the highest-risk endpoint.
        if request.method == "POST" and path.endswith("/auth/login"):
            d = await check(f"rl:login:{ip}", limit=LOGIN_LIMIT[0], window_seconds=LOGIN_LIMIT[1])
            if not d.allowed:
                return _too_many(d.reset_seconds)

        # 2. Per-actor (or per-IP) write throttle.
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            actor = request.headers.get("authorization", "")
            actor_key = actor[-32:] if actor else ip   # safe slice; not parsing JWT here
            d = await check(f"rl:write:{actor_key}", limit=WRITE_LIMIT[0], window_seconds=WRITE_LIMIT[1])
            if not d.allowed:
                return _too_many(d.reset_seconds)

        response: Response = await call_next(request)
        return response
