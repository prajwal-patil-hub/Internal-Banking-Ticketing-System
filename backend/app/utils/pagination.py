"""Common pagination params for list endpoints."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query


@dataclass(slots=True)
class PageParams:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


def page_params(
    page: int = Query(1, ge=1, le=10_000),
    size: int = Query(20, ge=1, le=100),
) -> PageParams:
    return PageParams(page=page, size=size)
