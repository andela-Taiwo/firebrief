"""Database sessions that can only be obtained for a named tenant.

There is deliberately no way to get a session without one. If a caller has a
tenant, it sets the setting for the duration of one transaction; when the
transaction ends, the setting is gone, so a pooled connection cannot carry one
tenant's context into another request.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine


class MissingTenantError(RuntimeError):
    """Raised when a session is requested without a tenant."""


async def apply_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


@asynccontextmanager
async def tenant_session(
    engine: AsyncEngine, tenant_id: uuid.UUID | None
) -> AsyncGenerator[AsyncSession]:
    """A session inside a transaction whose RLS tenant is `tenant_id`."""
    if tenant_id is None or str(tenant_id).strip() == "":
        raise MissingTenantError("a tenant id is required for every database session")

    async with AsyncSession(engine, expire_on_commit=False) as session, session.begin():
        await apply_tenant(session, tenant_id)
        yield session


def make_engine(url: str, *, pool_size: int = 5) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, pool_size=pool_size)
