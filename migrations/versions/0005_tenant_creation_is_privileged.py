"""tenant creation is an operator action, not an API action

The tenants table had an INSERT policy scoped to the tenant's own id, which looks
safe but is not: any session holding an arbitrary UUID could create that tenant.
Creating a tenant is onboarding, so it belongs to a privileged path outside the
runtime role. The three per-command policies now cover SELECT and UPDATE only.

Revision ID: 0005_privileged_tenants
Revises: 0004_grants
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_privileged_tenants"
down_revision: str | None = "0004_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SELF_PREDICATE = "id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def upgrade() -> None:
    op.execute("drop policy tenant_self_insert on tenants")


def downgrade() -> None:
    op.execute(
        f"create policy tenant_self_insert on tenants for insert with check ({SELF_PREDICATE})"
    )
