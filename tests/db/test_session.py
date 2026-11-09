from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.db.models import User
from firebrief.db.session import MissingTenantError, tenant_session
from tests.db.data import TENANT_A, USER_B


async def test_a_tenant_session_sees_only_its_own_tenant(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, UUID(TENANT_A)) as session:
        users = (await session.execute(sa.select(User))).scalars().all()
    assert [user.email for user in users] == ["a@alpha.test"]


async def test_a_tenant_session_cannot_read_another_tenants_row(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, UUID(TENANT_A)) as session:
        found = (
            (await session.execute(sa.select(User).where(User.id == UUID(USER_B)))).scalars().all()
        )
    assert found == []


async def test_a_session_cannot_be_opened_without_a_tenant(app_engine: AsyncEngine) -> None:
    with pytest.raises(MissingTenantError):
        async with tenant_session(app_engine, None):
            pass


async def test_the_tenant_does_not_leak_to_the_next_connection(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, UUID(TENANT_A)) as session:
        await session.execute(sa.text("select 1"))

    async with app_engine.connect() as connection:
        leaked = (
            await connection.execute(sa.text("select current_setting('app.tenant_id', true)"))
        ).scalar_one()
    assert leaked in (None, ""), f"tenant setting survived the transaction: {leaked!r}"
