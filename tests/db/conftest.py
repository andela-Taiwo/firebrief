from __future__ import annotations

import asyncio
import os
import re
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


def _database_name(url: str) -> str:
    return (make_url(url).database or "").removesuffix("?database=firebrief_dev")


@pytest.fixture(scope="session")
def owner_url() -> str:
    if not _database_name(OWNER_URL).endswith("_test"):
        raise pytest.UsageError(f"refusing to run against a non-test database URL: {OWNER_URL}")
    return OWNER_URL


@pytest.fixture(scope="session")
def app_url() -> str:
    if not _database_name(APP_URL).endswith("_test"):
        raise pytest.UsageError(f"refusing to run against a non-test database URL: {APP_URL}")
    return APP_URL


def _grant(owner_url: str, app_user: str) -> None:
    async def run() -> None:
        engine = create_async_engine(owner_url, poolclass=sa.pool.NullPool)
        try:
            async with engine.begin() as conn:
                await conn.execute(sa.text(f'grant usage on schema public to "{app_user}"'))
                await conn.execute(
                    sa.text(
                        f"grant select, insert, update, delete on all tables "
                        f'in schema public to "{app_user}"'
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.fixture(scope="session", autouse=True)
def migrated(owner_url: str, app_url: str) -> None:
    """Run the real migrations, then give the runtime role its privileges."""
    environment = {**os.environ, "DATABASE_URL": owner_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade failed:\n{result.stdout}\n{result.stderr}")

    app_user = make_url(app_url).username or ""
    if not re.fullmatch(r"[A-Za-z0-9_]+", app_user):
        raise RuntimeError(f"unexpected application role name: {app_user!r}")
    _grant(owner_url, app_user)


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


@pytest.fixture
async def seeded(owner_engine: AsyncEngine) -> None:
    await seed(owner_engine)
