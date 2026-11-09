from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.db.roles import UnsafeDatabaseRole, assert_safe_database_role


async def test_a_superuser_is_refused(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        with pytest.raises(UnsafeDatabaseRole, match="superuser"):
            await assert_safe_database_role(connection)


async def test_the_runtime_role_is_accepted(app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as connection:
        await assert_safe_database_role(connection)
