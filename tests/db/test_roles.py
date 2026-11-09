from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from firebrief.db.roles import UnsafeDatabaseRole, assert_safe_database_role


def _engine_as(url: str, user: str, password: str) -> AsyncEngine:
    parsed = make_url(url).set(username=user, password=password)
    return create_async_engine(
        parsed.render_as_string(hide_password=False), poolclass=sa.pool.NullPool
    )


@pytest.fixture
async def bypass_rls_engine(owner_engine: AsyncEngine, app_url: str):
    async with owner_engine.begin() as connection:
        await connection.execute(sa.text("drop role if exists firebrief_bypass"))
        await connection.execute(
            sa.text(
                "create role firebrief_bypass login password 'bypass_dev' nosuperuser bypassrls"
            )
        )
    engine = _engine_as(app_url, "firebrief_bypass", "bypass_dev")
    try:
        yield engine
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.execute(sa.text("drop role if exists firebrief_bypass"))


@pytest.fixture
async def owning_engine(owner_engine: AsyncEngine, app_url: str):
    async with owner_engine.begin() as connection:
        await connection.execute(sa.text("drop role if exists firebrief_owning"))
        await connection.execute(
            sa.text("create role firebrief_owning login password 'owning_dev' nosuperuser")
        )
        await connection.execute(sa.text("create table canary_owned (id int)"))
        await connection.execute(sa.text("alter table canary_owned owner to firebrief_owning"))
    engine = _engine_as(app_url, "firebrief_owning", "owning_dev")
    try:
        yield engine
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.execute(sa.text("drop table if exists canary_owned"))
            await connection.execute(sa.text("drop role if exists firebrief_owning"))


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
