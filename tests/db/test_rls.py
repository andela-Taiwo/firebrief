from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

TENANT_TABLES = {"users", "memberships"}
SELF_SCOPED_TABLES = {"tenants"}
REVIEWED_GLOBAL_TABLES = {"alembic_version"}

# What the invariant test insists on. Checking that *a* policy exists is not
# enough: a policy of USING (true) would pass that and protect nothing.
STANDARD_POLICY = ("tenant_id", "app.tenant_id", "nullif", "::uuid")
SELF_POLICY = ("app.tenant_id", "nullif", "::uuid")

TENANT_A = "018f0000-0000-7000-8000-000000000001"
TENANT_B = "018f0000-0000-7000-8000-000000000002"
USER_A = "018f0000-0000-7000-8000-000000000011"
USER_B = "018f0000-0000-7000-8000-000000000012"


async def tables(conn: AsyncConnection) -> set[str]:
    result = await conn.execute(
        sa.text("select tablename from pg_tables where schemaname = 'public'")
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
    async with owner_engine.connect() as conn:
        found = await tables(conn)
    unreviewed = found - TENANT_TABLES - SELF_SCOPED_TABLES - REVIEWED_GLOBAL_TABLES
    assert not unreviewed, (
        f"tables are neither tenant-scoped nor on the reviewed global list: {sorted(unreviewed)}"
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
                    where n.nspname = 'public' and c.relkind = 'r'
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


async def test_policies_use_the_standard_expression(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    """
                    select tablename, policyname, qual, with_check
                    from pg_policies
                    where schemaname = 'public'
                    """
                )
            )
        ).all()

    policies: dict[str, list[tuple[str, str, str]]] = {}
    for table, name, qual, check in rows:
        policies.setdefault(table, []).append((name, qual or "", check or ""))

    for table, fragments in (
        *[(t, STANDARD_POLICY) for t in sorted(TENANT_TABLES)],
        *[(t, SELF_POLICY) for t in sorted(SELF_SCOPED_TABLES)],
    ):
        found = policies.get(table, [])
        assert found, f"{table}: no policy, so nothing protects it"
        for name, qual, check in found:
            for expression in (qual, check):
                normalised = expression.lower().replace(" ", "")
                for fragment in fragments:
                    assert fragment in normalised, (
                        f"{table}.{name}: expression {expression!r} is not the standard "
                        f"tenant policy (missing {fragment!r})"
                    )
                assert normalised not in {"true", "(true)"}, (
                    f"{table}.{name}: USING (true) protects nothing"
                )


async def _seed(engine: AsyncEngine) -> None:
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
                "ma": "018f0000-0000-7000-8000-000000000021",
                "mb": "018f0000-0000-7000-8000-000000000022",
                "a": TENANT_A,
                "b": TENANT_B,
                "ua": USER_A,
                "ub": USER_B,
            },
        )


@pytest.fixture
async def seeded(owner_engine: AsyncEngine) -> None:
    await _seed(owner_engine)


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


async def test_a_tenant_sees_only_its_own_rows(app_engine: AsyncEngine, seeded: None) -> None:
    async with app_engine.begin() as conn:
        await conn.execute(sa.text("select set_config('app.tenant_id', :t, true)"), {"t": TENANT_A})
        tenants = (await conn.execute(sa.text("select name from tenants"))).scalars().all()
        users = (await conn.execute(sa.text("select email from users"))).scalars().all()

    assert tenants == ["Alpha"]
    assert users == ["a@alpha.test"]


async def test_a_tenant_cannot_read_another_tenants_row(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with app_engine.begin() as conn:
        await conn.execute(sa.text("select set_config('app.tenant_id', :t, true)"), {"t": TENANT_A})
        rows = (
            (await conn.execute(sa.text("select email from users where id = :id"), {"id": USER_B}))
            .scalars()
            .all()
        )
    assert rows == []


async def test_a_tenant_cannot_update_or_delete_another_tenants_row(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with app_engine.begin() as conn:
        await conn.execute(sa.text("select set_config('app.tenant_id', :t, true)"), {"t": TENANT_A})
        updated = await conn.execute(
            sa.text("update users set name = 'hacked' where id = :id"), {"id": USER_B}
        )
        deleted = await conn.execute(sa.text("delete from users where id = :id"), {"id": USER_B})
    assert updated.rowcount == 0
    assert deleted.rowcount == 0


async def test_a_tenant_cannot_insert_a_row_for_another_tenant(
    app_engine: AsyncEngine, seeded: None
) -> None:
    async with app_engine.begin() as conn:
        await conn.execute(sa.text("select set_config('app.tenant_id', :t, true)"), {"t": TENANT_A})
        with pytest.raises(DBAPIError):
            await conn.execute(
                sa.text(
                    "insert into users (id, tenant_id, email, name) "
                    "values (:id, :t, 'x@beta.test', 'X')"
                ),
                {"id": "018f0000-0000-7000-8000-000000000098", "t": TENANT_B},
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
    assert "DELETE" not in commands, "deleting a tenant cascades to all of its data"
