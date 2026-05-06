"""Security headers middleware.

Hardens responses with the canonical browser-side defenses:
  - HSTS                           (force HTTPS for 6 months, includeSubDomains)
  - X-Content-Type-Options         (no MIME sniffing)
  - X-Frame-Options                (deny clickjacking)
  - Referrer-Policy                (strip on cross-origin)
  - Permissions-Policy             (deny powerful features by default)
  - Content-Security-Policy        (script-src self, no inline)
  - Cross-Origin-Opener-Policy     (isolate window opener)
  - Cross-Origin-Resource-Policy   (cross-site reads off)

HSTS only emits in production to avoid breaking dev over plain http.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://rsms.me; "
            "font-src 'self' https://rsms.me data:; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' http://localhost:8000 ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'",
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")

        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=15552000; includeSubDomains; preload",
            )
        return response
