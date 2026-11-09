from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# The harness refuses anything that is not plainly a test database. The check is
# made twice: once on the URL here, and once against the server's own
# current_database() (see tests/db/test_rls.py), because a ?database= override
# in the URL would otherwise slip past.
OWNER_URL = os.environ.get(
    "FIREBRIEF_TEST_DATABASE_URL",
    "postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_test",
)
APP_URL = os.environ.get(
    "FIREBRIEF_APP_DATABASE_URL",
    "postgresql+asyncpg://firebrief_app:firebrief_app_dev@127.0.0.1:55433/firebrief_test",
)


@pytest.fixture(scope="session")
def owner_url() -> str:
    if "_test" not in OWNER_URL.rsplit("/", 1)[-1]:
        raise pytest.UsageError(f"refusing to run against a non-test database URL: {OWNER_URL}")
    return OWNER_URL


@pytest.fixture(scope="session")
def app_url() -> str:
    if "_test" not in APP_URL.rsplit("/", 1)[-1]:
        raise pytest.UsageError(f"refusing to run against a non-test database URL: {APP_URL}")
    return APP_URL


@pytest.fixture
async def owner_engine(owner_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(owner_url, poolclass=sa.pool.NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(app_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(app_url, poolclass=sa.pool.NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()
