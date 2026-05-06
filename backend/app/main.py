"""FastAPI application factory.

Wires:
  - logging
  - CORS
  - request-context middleware
  - exception handlers
  - v1 API routers

Future phases will plug in: auth, RBAC, rate limiting, SLA scheduler,
Prometheus metrics — each behind a clear extension point.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import (
    audit, auth, branches, categories, dashboard, escalations, health,
    mfa, notifications, sla, teams, tickets, users,
)
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import aclose as rate_limit_aclose
from app.middleware.audit_context import AuditContextMiddleware
from app.middleware.metrics import MetricsMiddleware, metrics_response
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.workers.sla_scheduler import scheduler as sla_scheduler

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    configure_logging()
    log.info("app_starting", env=settings.APP_ENV, name=settings.APP_NAME)
    sla_scheduler.start()
    try:
        yield
    finally:
        await sla_scheduler.stop()
        await rate_limit_aclose()
        log.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # Middleware: Starlette runs them in *reverse* registration order, so the
    # last one added is outermost. We want order on request:
    #   RequestContext  -> SecurityHeaders -> Metrics -> RateLimit -> AuditContext -> handler
    # which means registering handler-side first.
    app.add_middleware(AuditContextMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    @app.get("/metrics", include_in_schema=False)
    async def _metrics() -> object:
        return metrics_response()

    # v1 routers
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(branches.router, prefix="/api/v1")
    app.include_router(categories.router, prefix="/api/v1")
    app.include_router(teams.router, prefix="/api/v1")
    app.include_router(tickets.router, prefix="/api/v1")
    app.include_router(sla.router, prefix="/api/v1")
    app.include_router(escalations.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(dashboard.router, prefix="/api/v1")
    app.include_router(mfa.router, prefix="/api/v1")

    return app


app = create_app()
