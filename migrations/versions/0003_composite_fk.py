"""tenant-aware foreign keys

A plain foreign key from memberships(user_id) to users(id) lets one tenant point
at another tenant's user: referential integrity checks run as the owner and
bypass row level security. The key itself has to carry the tenant.

Revision ID: 0003_composite_fk
Revises: 0002_tenant_isolation
Create Date: 2026-11-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_composite_fk"
down_revision: str | None = "0002_tenant_isolation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table users add constraint uq_users_tenant_id_id unique (tenant_id, id)")
    op.execute("alter table memberships drop constraint fk_memberships_user_id_users")
    op.execute(
        "alter table memberships add constraint fk_memberships_tenant_user "
        "foreign key (tenant_id, user_id) references users (tenant_id, id)"
    )


def downgrade() -> None:
    op.execute("alter table memberships drop constraint fk_memberships_tenant_user")
    op.execute(
        "alter table memberships add constraint fk_memberships_user_id_users "
        "foreign key (user_id) references users (id)"
    )
    op.execute("alter table users drop constraint uq_users_tenant_id_id")
