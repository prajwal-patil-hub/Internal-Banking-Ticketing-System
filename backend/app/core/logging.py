"""Structured JSON logging with structlog.

Every log line carries: timestamp, level, logger, event, request_id (when set
by middleware), and any kwargs passed to the logger call. JSON makes logs
trivially consumable by ELK / Loki / CloudWatch.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def configure_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_production:
        renderers = [structlog.processors.JSONRenderer()]
    else:
        # Disable ANSI colors when stdout isn't a TTY (e.g. when piped to a
        # file or to docker logs without a tty). Otherwise the file ends up
        # full of `\x1b[...m` escape codes that Notepad can't render.
        colors = sys.stdout.isatty()
        renderers = [structlog.dev.ConsoleRenderer(colors=colors)]

    structlog.configure(
        processors=shared_processors
        + [structlog.processors.format_exc_info, *renderers],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
