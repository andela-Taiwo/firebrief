"""magic links and sessions

Tenant-owned like every other tenant table: both carry tenant_id and the standard policy,
and the runtime role gets only the statements it needs.

Revision ID: 0009_auth
Revises: 0008_retrieval_index
Create Date: 2026-11-10
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_auth"
down_revision: str | None = "0008_retrieval_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("auth_magic_links", "auth_sessions")
PREDICATE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"


def _role() -> str:
    role = os.environ.get("FIREBRIEF_APP_ROLE", "firebrief_app")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"FIREBRIEF_APP_ROLE is not a valid identifier: {role!r}")
    return role


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "auth_magic_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_auth_magic_links_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_magic_links_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_magic_links")),
        sa.UniqueConstraint("tenant_id", "token_hash", name="uq_auth_links_tenant_hash"),
    )
    op.create_index(op.f("ix_auth_magic_links_tenant_id"), "auth_magic_links", ["tenant_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_auth_sessions_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("tenant_id", "token_hash", name="uq_auth_sessions_tenant_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_tenant_id"), "auth_sessions", ["tenant_id"])

    for table in TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy tenant_isolation on {table} for all "
            f"using ({PREDICATE}) with check ({PREDICATE})"
        )

    role = _role()
    for table, privileges in (
        ("auth_magic_links", "select, insert, update"),
        ("auth_sessions", "select, insert, update"),
    ):
        op.execute(f'revoke all on {table} from "{role}"')
        op.execute(f'grant {privileges} on {table} to "{role}"')


def downgrade() -> None:
    role = _role()
    for table in TABLES:
        op.execute(f'revoke all on {table} from "{role}"')
        op.execute(f"drop policy tenant_isolation on {table}")
        op.execute(f"alter table {table} no force row level security")
        op.execute(f"alter table {table} disable row level security")
    op.drop_index(op.f("ix_auth_sessions_tenant_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index(op.f("ix_auth_magic_links_tenant_id"), table_name="auth_magic_links")
    op.drop_table("auth_magic_links")
