"""Test-wide environment defaults.

pytest imports conftest.py before any test module, so this is the cleanest
place to seed the env vars our settings require. Each setdefault() respects
anything the CI workflow has already pinned via `env:`.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test_secret_must_be_at_least_32_characters_long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("APP_ENV", "development")
