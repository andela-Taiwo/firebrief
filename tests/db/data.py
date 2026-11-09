"""Fixture data for the tenant isolation tests.

Two tenants, one user each, so a leak is visible as a row that should not be
there rather than as an empty result.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

TENANT_A = "018f0000-0000-7000-8000-000000000001"
TENANT_B = "018f0000-0000-7000-8000-000000000002"
USER_A = "018f0000-0000-7000-8000-000000000011"
USER_B = "018f0000-0000-7000-8000-000000000012"
MEMBERSHIP_A = "018f0000-0000-7000-8000-000000000021"
MEMBERSHIP_B = "018f0000-0000-7000-8000-000000000022"


async def seed(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(sa.text("truncate table memberships, users, tenants cascade"))
        await conn.execute(
            sa.text("insert into tenants (id, name) values (:a, 'Alpha'), (:b, 'Beta')"),
            {"a": TENANT_A, "b": TENANT_B},
        )
        await conn.execute(
            sa.text(
                """
                insert into users (id, tenant_id, email, name) values
                    (:ua, :a, 'a@alpha.test', 'Ada'),
                    (:ub, :b, 'b@beta.test', 'Ben')
                """
            ),
            {"ua": USER_A, "ub": USER_B, "a": TENANT_A, "b": TENANT_B},
        )
        await conn.execute(
            sa.text(
                """
                insert into memberships (id, tenant_id, user_id, role) values
                    (:ma, :a, :ua, 'owner'),
                    (:mb, :b, :ub, 'owner')
                """
            ),
            {
                "ma": MEMBERSHIP_A,
                "mb": MEMBERSHIP_B,
                "a": TENANT_A,
                "b": TENANT_B,
                "ua": USER_A,
                "ub": USER_B,
            },
        )
