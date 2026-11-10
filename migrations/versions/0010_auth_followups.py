"""auth follow-ups: ended_reason, normalised emails, one email constraint

Three deferred decisions from the auth reviews, done before the audit log depends on them:

- `ended_reason` distinguishes a link that was used from one that was superseded, which
  `consumed_at` alone cannot express. It is tied to `consumed_at` by a check and made
  write-once by a trigger, so the two cannot drift apart and a reason cannot be rewritten.
- Emails are normalised by the database on write, so onboarding cannot store a mixed-case
  address that bypasses the `lower(email)` index. The backfill refuses to run if
  normalisation would collide two addresses; on a fresh database it does nothing. It does
  touch `updated_at` on every user row, unavoidably.
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
    # Emails are unique on lower(email) but not on the trimmed form, so trimming could
    # collide two rows. Refuse loudly rather than half-migrating.
    op.execute(
        """
        do $$
        declare collisions int;
        begin
            select count(*) into collisions from (
                select tenant_id, lower(btrim(email))
                from users
                group by 1, 2
                having count(*) > 1
            ) duplicate;
            if collisions > 0 then
                raise exception
                    'cannot normalise emails: % address(es) collide after trimming', collisions;
            end if;
        end;
        $$
        """
    )
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
    # Rows consumed before this migration cannot be attributed; say so rather than guess.
    op.execute("update auth_magic_links set ended_reason = 'unknown' where consumed_at is not null")
    op.execute(
        "alter table auth_magic_links add constraint ck_auth_magic_links_ended_reason_allowed "
        "check (ended_reason in ('used', 'superseded', 'unknown'))"
    )
    op.execute(
        "alter table auth_magic_links add constraint ck_auth_magic_links_consumed_with_reason "
        "check ((consumed_at is null) = (ended_reason is null))"
    )
    op.execute(
        """
        create function forbid_reason_change() returns trigger
        language plpgsql as $$
        begin
            if old.consumed_at is not null or old.ended_reason is not null then
                raise exception 'a magic link ending is write-once';
            end if;
            return new;
        end;
        $$
        """
    )
    op.execute(
        "create trigger auth_magic_links_ended_once before update on auth_magic_links "
        "for each row execute function forbid_reason_change()"
    )

    role = _role()
    op.execute(f'grant update (consumed_at, ended_reason) on auth_magic_links to "{role}"')


def downgrade() -> None:
    role = _role()
    op.execute(f'revoke update (ended_reason) on auth_magic_links from "{role}"')
    op.execute("drop trigger auth_magic_links_ended_once on auth_magic_links")
    op.execute("drop function forbid_reason_change()")
    op.execute(
        "alter table auth_magic_links drop constraint ck_auth_magic_links_consumed_with_reason"
    )
    op.execute(
        "alter table auth_magic_links drop constraint ck_auth_magic_links_ended_reason_allowed"
    )
    op.drop_column("auth_magic_links", "ended_reason")

    op.execute("alter table users add constraint uq_users_tenant_email unique (tenant_id, email)")
    op.execute("drop trigger users_normalise_email on users")
    op.execute("drop function normalise_user_email()")
