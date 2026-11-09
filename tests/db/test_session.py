from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from firebrief.db.models import User
from firebrief.db.session import MissingTenantError, tenant_session
from tests.db.data import TENANT_A, TENANT_B, USER_B


async def test_a_tenant_session_sees_only_its_own_tenant(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        names = (await session.execute(sa.text("select name from tenants"))).scalars().all()
    assert names == ["Alpha"]


async def test_a_tenant_session_cannot_read_another_tenants_row(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        found = (
            (
                await session.execute(
                    sa.text("select email from users where id = :id"), {"id": USER_B}
                )
            )
            .scalars()
            .all()
        )
    assert found == []


async def test_a_session_cannot_be_opened_without_a_tenant(app_engine: AsyncEngine) -> None:
    with pytest.raises(MissingTenantError):
        async with tenant_session(app_engine, None):
            pass


async def test_the_tenant_does_not_leak_to_the_next_connection(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        await session.execute(sa.text("select 1"))

    async with app_engine.connect() as connection:
        leaked = (
            await connection.execute(sa.text("select current_setting('app.tenant_id', true)"))
        ).scalar_one()
    assert leaked in (None, ""), f"tenant setting survived the transaction: {leaked!r}"


async def test_the_tenant_does_not_leak_between_transactions_on_one_connection(
    app_url: str, seeded: None
) -> None:
    """One pooled connection, two transactions, two tenants: no carry-over."""
    engine = create_async_engine(app_url, pool_size=1, max_overflow=0)
    try:
        async with tenant_session(engine, uuid.UUID(TENANT_A)) as session:
            first = (await session.execute(sa.text("select name from tenants"))).scalars().all()

        async with tenant_session(engine, uuid.UUID(TENANT_B)) as session:
            second = (await session.execute(sa.text("select name from tenants"))).scalars().all()
    finally:
        await engine.dispose()

    assert [first, second] == [["Alpha"], ["Beta"]]


async def test_the_orm_sees_only_the_current_tenant_rows(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        users = (await session.execute(sa.select(User))).scalars().all()
    assert [user.email for user in users] == ["a@alpha.test"]
