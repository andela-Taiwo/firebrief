from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from firebrief.db.session import tenant_session
from tests.db.data import TENANT_A, TENANT_B, USER_B

TENANT_TABLES = {"users", "memberships"}
SELF_SCOPED_TABLES = {"tenants"}
REVIEWED_GLOBAL_TABLES = {"alembic_version"}

# One canonical expression, compared exactly after normalisation. Fragment
# matching would accept "... OR true"; this cannot.
TENANT_EXPRESSION = "(tenant_id=(nullif(current_setting('app.tenant_id',true),''))::uuid)"
SELF_EXPRESSION = "(id=(nullif(current_setting('app.tenant_id',true),''))::uuid)"

# cmd -> the single expression that policy must carry. SELECT policies have no
# WITH CHECK, INSERT policies have no USING, so only what exists is compared.
EXPECTED_POLICIES: dict[str, dict[str, str]] = {
    "users": {"ALL": TENANT_EXPRESSION},
    "memberships": {"ALL": TENANT_EXPRESSION},
    # No INSERT: creating a tenant is an operator action (0005).
    "tenants": {
        "SELECT": SELF_EXPRESSION,
        "UPDATE": SELF_EXPRESSION,
    },
}


def rowcount(result: Any) -> int:
    """SQLAlchemy types execute() as Result; DELETE returns a CursorResult."""
    return cast(CursorResult[Any], result).rowcount


def normalise(expression: str) -> str:
    """PostgreSQL's own rendering, minus whitespace and the ::text casts.

    Parentheses are kept: removing them would turn nullif(...) into
    nullif..., which is a different expression. The canonical form is what the
    pinned PostgreSQL major version renders, so a formatting change fails the
    test loudly rather than silently.
    """
    without_casts = expression.lower().replace("::text", "")
    return "".join(without_casts.split())


async def tables(conn: AsyncConnection) -> set[str]:
    result = await conn.execute(
        sa.text(
            """
            select c.relname
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind in ('r', 'p')
            """
        )
    )
    return set(result.scalars().all())


async def relations(conn: AsyncConnection) -> set[str]:
    """Every relation a query could read: tables, partitions and views."""
    result = await conn.execute(
        sa.text(
            """
            select c.relname
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm')
            """
        )
    )
    return set(result.scalars().all())


async def test_the_database_is_a_test_database(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        name = (await conn.execute(sa.text("select current_database()"))).scalar_one()
    assert name.endswith("_test"), f"refusing to run against {name}"


async def test_expected_tables_exist(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        found = await tables(conn)
    missing = (TENANT_TABLES | SELF_SCOPED_TABLES) - found
    assert not missing, f"tenant tables missing: {sorted(missing)}"


async def test_every_table_is_tenant_scoped_or_reviewed_global(
    owner_engine: AsyncEngine,
) -> None:
    """Tables, partitions and views all need a decision, not just tables."""
    async with owner_engine.connect() as conn:
        found = await relations(conn)
    unreviewed = found - TENANT_TABLES - SELF_SCOPED_TABLES - REVIEWED_GLOBAL_TABLES
    assert not unreviewed, (
        "tables are neither tenant-scoped nor on the reviewed global list: "
        f"{sorted(unreviewed)} (partitions are reviewed the same way as tables)"
    )


async def test_rls_is_enabled_and_forced(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    """
                    select c.relname, c.relrowsecurity, c.relforcerowsecurity
                    from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'public' and c.relkind in ('r', 'p')
                    """
                )
            )
        ).all()

    state = {name: (enabled, forced) for name, enabled, forced in rows}
    for table in TENANT_TABLES | SELF_SCOPED_TABLES:
        assert table in state, f"{table} is missing"
        enabled, forced = state[table]
        assert enabled, f"{table}: row level security is not enabled"
        assert forced, f"{table}: FORCE ROW LEVEL SECURITY is not set"


async def test_policies_are_the_standard_expressions(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    sa.text(
                        """
                    select tablename, policyname, permissive, roles, cmd, qual, with_check
                    from pg_policies
                    where schemaname = 'public'
                    """
                    )
                )
            )
            .mappings()
            .all()
        )

    by_table: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        by_table.setdefault(str(row["tablename"]), {})[str(row["cmd"])] = dict(row)

    for table, expected in EXPECTED_POLICIES.items():
        found = by_table.get(table, {})
        assert set(found) == set(expected), (
            f"{table}: expected commands {sorted(expected)}, found {sorted(found)}"
        )
        for command, expression in expected.items():
            policy = found[command]
            assert policy["permissive"] == "PERMISSIVE", (
                f"{table}.{command}: a restrictive policy is ANDed, not the standard"
            )
            assert list(policy["roles"]) == ["public"], (
                f"{table}.{command}: policy applies to {policy['roles']}, not to PUBLIC"
            )

            if command in ("SELECT", "UPDATE", "ALL"):
                qual = str(policy["qual"] or "")
                assert qual, f"{table}.{command}: no USING expression"
                assert normalise(qual) == expression, (
                    f"{table}.{command}: USING {qual!r} is not the standard policy"
                )

            if command in ("INSERT", "UPDATE", "ALL"):
                check = str(policy["with_check"] or "")
                assert check, f"{table}.{command}: no WITH CHECK expression"
                assert normalise(check) == expression, (
                    f"{table}.{command}: WITH CHECK {check!r} is not the standard policy"
                )


async def test_the_tenant_table_has_no_delete_policy(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        commands = (
            (
                await conn.execute(
                    sa.text(
                        "select cmd from pg_policies where schemaname = 'public' "
                        "and tablename = 'tenants'"
                    )
                )
            )
            .scalars()
            .all()
        )

    assert not {"DELETE", "ALL"} & set(commands), (
        "deleting a tenant cascades to all of its data, so no policy may permit it; "
        f"found {sorted(commands)}"
    )


async def test_deleting_a_tenant_is_refused_by_the_database(
    app_engine: AsyncEngine, seeded: None
) -> None:
    """DELETE is not granted on tenants, so this is a permission error, not a filter."""
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        with pytest.raises(DBAPIError, match="permission denied"):
            await session.execute(sa.text("delete from tenants where id = :id"), {"id": TENANT_A})


async def test_without_a_tenant_nothing_is_visible(app_engine: AsyncEngine, seeded: None) -> None:
    async with app_engine.begin() as conn:
        tenants = (await conn.execute(sa.text("select count(*) from tenants"))).scalar_one()
        users = (await conn.execute(sa.text("select count(*) from users"))).scalar_one()
    assert (tenants, users) == (0, 0)


async def test_without_a_tenant_writes_are_rejected(app_engine: AsyncEngine, seeded: None) -> None:
    async with app_engine.begin() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(
                sa.text(
                    "insert into users (id, tenant_id, email, name) "
                    "values (:id, :t, 'x@x.test', 'X')"
                ),
                {"id": "018f0000-0000-7000-8000-000000000099", "t": TENANT_A},
            )


async def test_a_tenant_sees_only_its_own_tenants_row(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        names = (await session.execute(sa.text("select name from tenants"))).scalars().all()
    assert names == ["Alpha"]


@pytest.mark.parametrize("table", sorted(TENANT_TABLES))
async def test_every_tenant_table_shows_only_its_own_rows(
    app_engine: AsyncEngine, seeded: None, table: str
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        count = (
            await session.execute(sa.text(f"select count(*) from {table}"))  # noqa: S608
        ).scalar_one()
    assert count == 1, f"{table}: expected one row for tenant A, found {count}"


async def test_a_tenant_cannot_read_another_tenants_row(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        rows = (
            (
                await session.execute(
                    sa.text("select email from users where id = :id"), {"id": USER_B}
                )
            )
            .scalars()
            .all()
        )
    assert rows == []


MUTATIONS: dict[str, tuple[str, str]] = {
    "users": (
        "update users set name = 'hacked' where tenant_id = :t",
        "delete from users where tenant_id = :t",
    ),
    "memberships": (
        "update memberships set role = 'viewer' where tenant_id = :t",
        "delete from memberships where tenant_id = :t",
    ),
}


@pytest.mark.parametrize("table", sorted(TENANT_TABLES))
async def test_a_tenant_cannot_update_or_delete_another_tenants_rows(
    app_engine: AsyncEngine, seeded: None, table: str
) -> None:
    update_sql, delete_sql = MUTATIONS[table]
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        updated = await session.execute(sa.text(update_sql), {"t": TENANT_B})
        deleted = await session.execute(sa.text(delete_sql), {"t": TENANT_B})
    assert rowcount(updated) == 0, f"{table}: a cross-tenant update touched rows"
    assert rowcount(deleted) == 0, f"{table}: a cross-tenant delete touched rows"


@pytest.mark.parametrize("table", sorted(TENANT_TABLES))
async def test_a_tenant_cannot_insert_a_row_for_another_tenant(
    app_engine: AsyncEngine, seeded: None, table: str
) -> None:
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        if table == "users":
            statement = sa.text(
                "insert into users (id, tenant_id, email, name) "
                "values (:id, :t, 'x@beta.test', 'X')"
            )
            params: dict[str, str] = {"id": "018f0000-0000-7000-8000-000000000098", "t": TENANT_B}
        else:
            statement = sa.text(
                "insert into memberships (id, tenant_id, user_id, role) "
                "values (:id, :t, :u, 'viewer')"
            )
            params = {
                "id": "018f0000-0000-7000-8000-000000000094",
                "t": TENANT_B,
                "u": USER_B,
            }
        with pytest.raises(DBAPIError):
            await session.execute(statement, params)


async def test_a_membership_cannot_point_at_another_tenants_user(
    app_engine: AsyncEngine, seeded: None
) -> None:
    """The foreign key carries the tenant, because RI checks bypass RLS."""
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                sa.text(
                    "insert into memberships (id, tenant_id, user_id, role) "
                    "values (:id, :t, :u, 'viewer')"
                ),
                {
                    "id": "018f0000-0000-7000-8000-000000000097",
                    "t": TENANT_A,
                    "u": USER_B,
                },
            )


async def test_a_membership_can_still_point_at_a_user_of_its_own_tenant(
    app_engine: AsyncEngine, seeded: None
) -> None:
    """Positive control: the composite key permits a legitimate membership."""
    second_user = "018f0000-0000-7000-8000-000000000013"
    async with tenant_session(app_engine, uuid.UUID(TENANT_A)) as session:
        await session.execute(
            sa.text(
                "insert into users (id, tenant_id, email, name) "
                "values (:id, :t, 'second@alpha.test', 'Second')"
            ),
            {"id": second_user, "t": TENANT_A},
        )
        await session.execute(
            sa.text(
                "insert into memberships (id, tenant_id, user_id, role) "
                "values (:id, :t, :u, 'viewer')"
            ),
            {
                "id": "018f0000-0000-7000-8000-000000000096",
                "t": TENANT_A,
                "u": second_user,
            },
        )
        count = (await session.execute(sa.text("select count(*) from memberships"))).scalar_one()
    assert count == 2


async def test_the_app_role_has_no_privileges_on_the_migration_table(
    app_engine: AsyncEngine,
) -> None:
    """alembic_version has no RLS, so the grant is the only thing protecting it.

    Checked privilege by privilege: an UPDATE alone would still fail without
    SELECT on the column, which would make a behavioural test pass for the wrong
    reason.
    """
    async with app_engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    sa.text(
                        """
                    select
                        has_table_privilege(current_user, 'alembic_version', 'SELECT') as sel,
                        has_table_privilege(current_user, 'alembic_version', 'INSERT') as ins,
                        has_table_privilege(current_user, 'alembic_version', 'UPDATE') as upd,
                        has_table_privilege(current_user, 'alembic_version', 'DELETE') as del
                    """
                    )
                )
            )
            .mappings()
            .one()
        )

    granted = [name for name, value in row.items() if value]
    assert not granted, f"the runtime role has {granted} on alembic_version"


async def test_views_use_security_invoker(owner_engine: AsyncEngine) -> None:
    """A view runs with its owner's rights unless told otherwise, bypassing RLS.

    No views exist yet. When the first one arrives it must be created with
    `security_invoker = true`; materialised views have no such option and need a
    separate review, because their contents are materialised as the refresher.
    """
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text(
                    """
                    select c.relname, c.reloptions
                    from pg_class c
                    join pg_namespace n on n.oid = c.relnamespace
                    where n.nspname = 'public' and c.relkind = 'v'
                    """
                )
            )
        ).all()

    for name, options in rows:
        assert options is not None, f"{name}: view has no reloptions at all"
        assert "security_invoker=true" in options, (
            f"{name}: create the view with security_invoker = true"
        )
