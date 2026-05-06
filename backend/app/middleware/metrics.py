"""Prometheus metrics middleware.

Exposes:
  - http_requests_total (Counter)        labels: method, path_template, status
  - http_request_duration_seconds (Hist) labels: method, path_template
  - app_info (Gauge)                     labels: env, name

Path templates use the FastAPI route's path (not the actual URL with
parameter values) so cardinality stays bounded.
"""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests",
    labelnames=("method", "path", "status"),
)
LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request duration",
    labelnames=("method", "path"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
APP_INFO = Gauge("app_info", "Application metadata", labelnames=("env", "name"))
APP_INFO.labels(env=settings.APP_ENV, name=settings.APP_NAME).set(1)


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path_template = self._template(request)
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start

        REQUESTS.labels(
            method=request.method, path=path_template, status=str(response.status_code),
        ).inc()
        LATENCY.labels(method=request.method, path=path_template).observe(elapsed)
        return response

    @staticmethod
    def _template(request: Request) -> str:
        # Try the matched route's path (e.g. /api/v1/tickets/{ticket_id}).
        route = request.scope.get("route")
        if route is not None and getattr(route, "path", None):
            return route.path
        return request.url.path
