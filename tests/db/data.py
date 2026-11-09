"""Fixture data for the tenant isolation tests.

Two tenants, one user each, so a leak is visible as a row that should not be
there rather than as an empty result.

Tenants are inserted as the owner, because creating a tenant is an onboarding
action with no INSERT policy (migration 0005). Everything else is written through
the runtime role, inside a tenant session, so the seed exercises the same policies
a real write would. The TRUNCATE is the other privileged statement.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.db.session import tenant_session

TENANT_A = "018f0000-0000-7000-8000-000000000001"
TENANT_B = "018f0000-0000-7000-8000-000000000002"
USER_A = "018f0000-0000-7000-8000-000000000011"
USER_B = "018f0000-0000-7000-8000-000000000012"
MEMBERSHIP_A = "018f0000-0000-7000-8000-000000000021"
MEMBERSHIP_B = "018f0000-0000-7000-8000-000000000022"


@dataclass(frozen=True)
class TenantFixture:
    tenant_id: str
    name: str
    user_id: str
    email: str
    person: str
    membership_id: str


FIXTURES = (
    TenantFixture(TENANT_A, "Alpha", USER_A, "a@alpha.test", "Ada", MEMBERSHIP_A),
    TenantFixture(TENANT_B, "Beta", USER_B, "b@beta.test", "Ben", MEMBERSHIP_B),
)


async def seed(owner_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    # Tenant creation is a privileged onboarding action (0005), so the fixtures
    # create tenants as the owner. Everything else is written through the
    # runtime role, inside a tenant session, exercising the same policies a real
    # write would.
    async with owner_engine.begin() as connection:
        await connection.execute(sa.text("truncate table memberships, users, tenants cascade"))
        for fixture in FIXTURES:
            await connection.execute(
                sa.text("insert into tenants (id, name) values (:id, :name)"),
                {"id": fixture.tenant_id, "name": fixture.name},
            )

    for fixture in FIXTURES:
        async with tenant_session(app_engine, uuid.UUID(fixture.tenant_id)) as session:
            await session.execute(
                sa.text(
                    "insert into users (id, tenant_id, email, name) "
                    "values (:id, :tenant_id, :email, :name)"
                ),
                {
                    "id": fixture.user_id,
                    "tenant_id": fixture.tenant_id,
                    "email": fixture.email,
                    "name": fixture.person,
                },
            )
            await session.execute(
                sa.text(
                    "insert into memberships (id, tenant_id, user_id, role) "
                    "values (:id, :tenant_id, :user_id, 'owner')"
                ),
                {
                    "id": fixture.membership_id,
                    "tenant_id": fixture.tenant_id,
                    "user_id": fixture.user_id,
                },
            )
