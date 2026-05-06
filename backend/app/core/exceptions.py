"""Application exception hierarchy and global handlers.

All domain errors inherit from `AppException`. Handlers translate them into
the standard JSON response envelope so the client never sees a raw stack trace.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


class AppException(Exception):
    """Base for all application-defined errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message
        self.details = details or {}
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppException):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found."


class ValidationError(AppException):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Invalid input."


class AuthenticationError(AppException):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Authentication required."


class AuthorizationError(AppException):
    status_code = 403
    code = "FORBIDDEN"
    message = "You are not allowed to perform this action."


class ConflictError(AppException):
    status_code = 409
    code = "CONFLICT"
    message = "Resource conflict."


class RateLimitError(AppException):
    status_code = 429
    code = "RATE_LIMITED"
    message = "Too many requests."


def _envelope(
    *,
    code: str,
    message: str,
    status_code: int,
    request_id: str | None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "data": None,
            "error": {"code": code, "message": message, "details": details or {}},
            "request_id": request_id,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def _app_exc(request: Request, exc: AppException) -> JSONResponse:
        log.warning(
            "app_exception",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
        )
        return _envelope(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=getattr(request.state, "request_id", None),
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _envelope(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            status_code=422,
            request_id=getattr(request.state, "request_id", None),
            details={"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _envelope(
            code="HTTP_ERROR",
            message=str(exc.detail),
            status_code=exc.status_code,
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_exception", path=request.url.path)
        return _envelope(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            status_code=500,
            request_id=getattr(request.state, "request_id", None),
        )
