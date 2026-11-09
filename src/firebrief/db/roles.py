"""Refuse to start if the database role can ignore row level security.

A superuser, a role with BYPASSRLS, or a role that is a *member* of either can
read every tenant's rows regardless of policy. Membership matters because
`SET ROLE` would reach the privileged role. This check runs at start-up so a
misconfiguration fails the deploy instead of silently removing the protection.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

_ROLE_QUERY = """
select
    r.rolname,
    r.rolsuper,
    r.rolbypassrls,
    exists (
        select 1
        from pg_auth_members am
        join pg_roles parent on parent.oid = am.roleid
        where am.member = r.oid
          and (parent.rolsuper or parent.rolbypassrls)
    ) as member_of_privileged,
    (
        select count(*)
        from pg_class c
        where c.relowner = r.oid and c.relkind in ('r', 'p')
    ) as owned_tables
from pg_roles r
where r.rolname = current_user
"""


class UnsafeDatabaseRole(RuntimeError):
    """The role in use can bypass row level security."""


async def assert_safe_database_role(connection: AsyncConnection) -> None:
    row = (await connection.execute(text(_ROLE_QUERY))).mappings().one()
    problems: list[str] = []
    if row["rolsuper"]:
        problems.append("is a superuser")
    if row["rolbypassrls"]:
        problems.append("has BYPASSRLS")
    if row["member_of_privileged"]:
        problems.append("is a member of a superuser or BYPASSRLS role")
    if row["owned_tables"]:
        problems.append(
            f"owns {row['owned_tables']} table(s), so it could drop or replace the policies"
        )
    if problems:
        raise UnsafeDatabaseRole(
            f"database role {row['rolname']!r} {' and '.join(problems)}; "
            "row level security would not apply, so the application refuses to start"
        )


async def verify_database_role(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await assert_safe_database_role(connection)
