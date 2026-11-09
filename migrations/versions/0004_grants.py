"""least privilege for the runtime role

Grants belong in a migration, not in a test fixture: production must get exactly
what the tests verify. The runtime role gets what it needs per table, and
nothing at all on alembic_version, which has no RLS and no business being
writable from the application.

The role name comes from FIREBRIEF_APP_ROLE (default firebrief_app), so an
environment can use its own name without editing this file.

Revision ID: 0004_grants
Revises: 0003_composite_fk
Create Date: 2026-11-09
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from alembic import op

revision: str = "0004_grants"
down_revision: str | None = "0003_composite_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ROLE = "firebrief_app"

# table -> privileges. Tenants are readable and updateable but never deletable:
# deleting a tenant cascades to every row it owns.
PRIVILEGES: dict[str, str] = {
    "tenants": "select, insert, update",
    "users": "select, insert, update, delete",
    "memberships": "select, insert, update, delete",
}


def _role() -> str:
    role = os.environ.get("FIREBRIEF_APP_ROLE", DEFAULT_ROLE)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"FIREBRIEF_APP_ROLE is not a valid identifier: {role!r}")
    return role


def upgrade() -> None:
    role = _role()
    op.execute(
        f"""
        do $$
        begin
            if not exists (select 1 from pg_roles where rolname = '{role}') then
                raise exception 'application role "%" does not exist; create it before'
                    ' running migrations', '{role}';
            end if;
        end
        $$
        """
    )
    op.execute(f'grant usage on schema public to "{role}"')
    # Revoke first: a role that already had wider grants (for example from a
    # previous incarnation of this schema) must not keep them.
    for table, privileges in PRIVILEGES.items():
        op.execute(f'revoke all on {table} from "{role}"')
        op.execute(f'grant {privileges} on {table} to "{role}"')
    # No privileges at all: the application never reads or writes its own
    # migration bookkeeping, and that table has no row level security.
    op.execute(f'revoke all on alembic_version from "{role}"')


def downgrade() -> None:
    role = _role()
    for table in PRIVILEGES:
        op.execute(f'revoke all on {table} from "{role}"')
    op.execute(f'revoke all on alembic_version from "{role}"')
    op.execute(f'revoke usage on schema public from "{role}"')
