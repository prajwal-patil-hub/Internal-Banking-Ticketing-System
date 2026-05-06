"""Standard API response envelope helpers.

All successful responses go through `ok()`. Errors are produced by exception
handlers in `app.core.exceptions`. Keeping this in one place guarantees a
consistent contract for every endpoint.
"""

from __future__ import annotations

from typing import Any


def ok(data: Any = None, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "meta": meta or {},
        "error": None,
    }


def paginated(items: list[Any], *, page: int, size: int, total: int) -> dict[str, Any]:
    return ok(
        items,
        meta={
            "pagination": {
                "page": page,
                "size": size,
                "total": total,
                "pages": (total + size - 1) // size if size else 0,
            }
        },
    )
