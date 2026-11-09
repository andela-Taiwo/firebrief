from __future__ import annotations

import re
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from firebrief.db.roles import UnsafeDatabaseRole, assert_safe_database_role


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", value):
        raise ValueError(f"unsafe identifier: {value!r}")
    return value


def _engine_as(url: str, user: str, password: str) -> AsyncEngine:
    parsed = make_url(url).set(username=user, password=password)
    return create_async_engine(
        parsed.render_as_string(hide_password=False), poolclass=sa.pool.NullPool
    )


def _suffix() -> str:
    """Roles are cluster-wide, so a shared server needs names that cannot collide."""
    return uuid.uuid4().hex[:8]


@pytest.fixture
async def bypass_rls_engine(owner_engine: AsyncEngine, app_url: str):
    role = _identifier(f"firebrief_bypass_{_suffix()}")
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text(f"create role {role} login password 'bypass_dev' nosuperuser bypassrls")
        )
    engine = _engine_as(app_url, role, "bypass_dev")
    try:
        yield engine
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.execute(sa.text(f"drop role {role}"))


@pytest.fixture
async def owning_engine(owner_engine: AsyncEngine, app_url: str):
    """A role that owns a table, in its own schema, dropped in teardown."""
    role = _identifier(f"firebrief_owning_{_suffix()}")
    schema = _identifier(f"canary_{_suffix()}")
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text(f"create role {role} login password 'owning_dev' nosuperuser")
        )
        await connection.execute(sa.text(f"create schema {schema}"))
        await connection.execute(sa.text(f"create table {schema}.owned (id int)"))
        await connection.execute(sa.text(f"alter table {schema}.owned owner to {role}"))
    engine = _engine_as(app_url, role, "owning_dev")
    try:
        yield engine
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.execute(sa.text(f"drop schema {schema} cascade"))
            await connection.execute(sa.text(f"drop role {role}"))


async def test_a_superuser_is_refused(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        with pytest.raises(UnsafeDatabaseRole, match="superuser"):
            await assert_safe_database_role(connection)


async def test_a_bypassrls_role_is_refused(bypass_rls_engine: AsyncEngine) -> None:
    async with bypass_rls_engine.connect() as connection:
        with pytest.raises(UnsafeDatabaseRole, match="BYPASSRLS"):
            await assert_safe_database_role(connection)


async def test_a_role_that_owns_tables_is_refused(owning_engine: AsyncEngine) -> None:
    async with owning_engine.connect() as connection:
        with pytest.raises(UnsafeDatabaseRole, match="owns"):
            await assert_safe_database_role(connection)


async def test_the_runtime_role_is_accepted(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        await assert_safe_database_role(connection)
