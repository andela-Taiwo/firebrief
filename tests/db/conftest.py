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


async def _assert_server_is_test_database(engine: AsyncEngine) -> None:
    """Ask the server what database this really is, before anything destructive."""
    async with engine.connect() as connection:
        name = (await connection.execute(sa.text("select current_database()"))).scalar_one()
    if not str(name).endswith("_test"):
        raise RuntimeError(f"refusing to run against {name}: not a *_test database")


@pytest.fixture(scope="session")
def owner_url() -> str:
    return _require_test_database(OWNER_URL)


@pytest.fixture(scope="session")
def app_url() -> str:
    return _require_test_database(APP_URL)


def _grant(owner_url_value: str, app_user: str) -> None:
    async def run() -> None:
        engine = create_async_engine(owner_url_value, poolclass=sa.pool.NullPool)
        try:
            async with engine.begin() as connection:
                await connection.execute(sa.text(f'grant usage on schema public to "{app_user}"'))
                await connection.execute(
                    sa.text(
                        f"grant select, insert, update, delete on all tables "
                        f'in schema public to "{app_user}"'
                    ),
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
        await _assert_server_is_test_database(engine)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def app_engine(app_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(app_url, poolclass=sa.pool.NullPool)
    try:
        await _assert_server_is_test_database(engine)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def seeded(owner_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    await seed(owner_engine, app_engine)
