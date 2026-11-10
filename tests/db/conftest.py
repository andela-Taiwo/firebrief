"""Database fixtures.

Roles are cluster-wide in PostgreSQL, not per-database, so the role tests create
roles with a unique suffix and drop them in teardown. That requires the owner
role to have CREATEROLE (it is the container superuser in development and CI).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.db.data import seed

REPO_ROOT = Path(__file__).resolve().parents[2]

OWNER_URL = os.environ.get(
    "FIREBRIEF_TEST_DATABASE_URL",
    "postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_test",
)
APP_URL = os.environ.get(
    "FIREBRIEF_APP_DATABASE_URL",
    "postgresql+asyncpg://firebrief_app:firebrief_app_dev@127.0.0.1:55433/firebrief_test",
)


def _require_test_database(url: str) -> str:
    """Refuse anything that is not a *_test database, read from the URL.

    make_url strips the query string, so `?database=firebrief_dev` cannot hide
    the real name from this check.
    """
    name = make_url(url).database or ""
    if not name.endswith("_test"):
        raise pytest.UsageError(f"refusing to run against a non-test database URL: {url}")
    return url


async def _database_name(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        return str((await connection.execute(sa.text("select current_database()"))).scalar_one())


def _assert_is_test_database(name: str) -> None:
    if not name.endswith("_test"):
        raise RuntimeError(f"refusing to run against {name}: not a *_test database")


def _assert_server_is_test_database(engine: AsyncEngine) -> None:
    _assert_is_test_database(asyncio.run(_database_name(engine)))


@pytest.fixture(scope="session")
def owner_url() -> str:
    return _require_test_database(OWNER_URL)


@pytest.fixture(scope="session")
def app_url() -> str:
    return _require_test_database(APP_URL)


@pytest.fixture(scope="session", autouse=True)
def migrated(owner_url: str) -> None:
    """Prove the server is a test database, then run the real migrations.

    The check happens before alembic, not after: a ?database= query parameter
    could redirect the connection, and migrations are destructive.
    """
    engine = create_async_engine(owner_url, poolclass=sa.pool.NullPool)
    try:
        _assert_server_is_test_database(engine)
    finally:
        asyncio.run(engine.dispose())

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": owner_url},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture
async def owner_engine(owner_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(owner_url, poolclass=sa.pool.NullPool)
    try:
        _assert_is_test_database(await _database_name(engine))
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(app_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(app_url, poolclass=sa.pool.NullPool)
    try:
        _assert_is_test_database(await _database_name(engine))
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def seeded(owner_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await seed(owner_engine, app_engine)


@pytest.fixture(autouse=True)
async def empty_corpus(owner_engine: AsyncEngine) -> None:
    """Reset the corpus between tests.

    TRUNCATE is itself guarded, so the owner disables triggers for this
    transaction only. That is the owner bypass ADR 0003 records.
    """
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("select set_config('session_replication_role', 'replica', true)")
        )
        await connection.execute(
            sa.text("truncate table chunks, sections, document_versions, documents cascade")
        )
