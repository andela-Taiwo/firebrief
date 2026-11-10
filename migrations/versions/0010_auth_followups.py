"""auth follow-ups: ended_reason, normalised emails, one email constraint

Three deferred decisions from the auth reviews, done before the audit log depends on them:

- `ended_reason` distinguishes a link that was used from one that was superseded, which the
  audit log needs and `consumed_at` alone cannot express.
- Emails are normalised by the database on write, so onboarding cannot store a mixed-case
  address that bypasses the `lower(email)` index.
- The case-sensitive unique constraint is dropped now that the index covers it.

Revision ID: 0010_auth_followups
Revises: 0009_auth
Create Date: 2026-11-10
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_auth_followups"
down_revision: str | None = "0009_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role() -> str:
    role = os.environ.get("FIREBRIEF_APP_ROLE", "firebrief_app")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"FIREBRIEF_APP_ROLE is not a valid identifier: {role!r}")
    return role


def upgrade() -> None:
    op.execute("update users set email = lower(btrim(email))")
    op.execute(
        """
        create function normalise_user_email() returns trigger
        language plpgsql as $$
        begin
            new.email = lower(btrim(new.email));
            return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger users_normalise_email before insert or update of email on users "
        "for each row execute function normalise_user_email()"
    )
    op.execute("alter table users drop constraint uq_users_tenant_email")

    op.add_column(
        "auth_magic_links", sa.Column("ended_reason", sa.String(length=20), nullable=True)
    )
    op.execute(
        "alter table auth_magic_links add constraint ck_auth_magic_links_ended_reason "
        "check (ended_reason in ('used', 'superseded'))"
    )

    role = _role()
    op.execute(f'grant update (consumed_at, ended_reason) on auth_magic_links to "{role}"')


def downgrade() -> None:
    role = _role()
    op.execute(f'revoke update (ended_reason) on auth_magic_links from "{role}"')
    op.execute("alter table auth_magic_links drop constraint ck_auth_magic_links_ended_reason")
    op.drop_column("auth_magic_links", "ended_reason")

    op.execute("alter table users add constraint uq_users_tenant_email unique (tenant_id, email)")
    op.execute("drop trigger users_normalise_email on users")
    op.execute("drop function normalise_user_email()")
