"""tenant isolation: policies, FORCE, and one clock for updated_at

Revision ID: 0002_tenant_isolation
Revises: e21605258620
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_tenant_isolation"
down_revision: str | None = "e21605258620"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_PREDICATE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"
SELF_PREDICATE = "id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    # One clock: updated_at moves in the database, so bulk updates and raw SQL
    # move it too, and application code cannot backdate it.
    op.execute(
        """
        create function set_updated_at() returns trigger
        language plpgsql as $$
        begin
            new.updated_at = now();
            return new;
        end;
        $$
        """
    )
    for table in ("tenants", "users", "memberships"):
        op.execute(
            f"create trigger {table}_set_updated_at before update on {table} "
            "for each row execute function set_updated_at()"
        )

    # ENABLE makes policies apply to everyone except the owner; FORCE makes them
    # apply to the owner too, which matters because on managed hosts the runtime
    # role often is the owner.
    for table in ("tenants", "users", "memberships"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")

    for table in ("users", "memberships"):
        op.execute(
            f"create policy tenant_isolation on {table} for all "
            f"using ({TENANT_PREDICATE}) with check ({TENANT_PREDICATE})"
        )

    # The tenants table is scoped by its own id. Policies are created per
    # command with no DELETE policy at all: deleting a tenant cascades to every
    # row it owns, so offboarding is an operator action, not an API one.
    op.execute(f"create policy tenant_self_select on tenants for select using ({SELF_PREDICATE})")
    op.execute(
        f"create policy tenant_self_insert on tenants for insert with check ({SELF_PREDICATE})"
    )
    op.execute(
        f"create policy tenant_self_update on tenants for update "
        f"using ({SELF_PREDICATE}) with check ({SELF_PREDICATE})"
    )


def downgrade() -> None:
    for table, policies in (
        ("tenants", ("tenant_self_select", "tenant_self_insert", "tenant_self_update")),
        ("users", ("tenant_isolation",)),
        ("memberships", ("tenant_isolation",)),
    ):
        for policy in policies:
            op.execute(f"drop policy {policy} on {table}")

    for table in ("tenants", "users", "memberships"):
        op.execute(f"alter table {table} no force row level security")
        op.execute(f"alter table {table} disable row level security")
        op.execute(f"drop trigger {table}_set_updated_at on {table}")

    op.execute("drop function set_updated_at()")
