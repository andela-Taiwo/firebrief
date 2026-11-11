"""durable budget counters and reservations

The budget lived in process memory, so a restart forgot what had been spent. These two
tables are the durable form: one row per (scope, period, period start) for the counters,
one row per reservation.

They are operator-trusted tables, keyed by the opaque scope ids the budget hierarchy already
uses. Row-level security does not apply because the ledger has no tenant column; every read
goes through `BudgetService`, and the RBAC feature will decide whether that changes.

Revision ID: 0011_budget_ledger
Revises: 0010_auth_followups
Create Date: 2026-11-11
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_budget_ledger"
down_revision: str | None = "0010_auth_followups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("budget_counters", "budget_reservations")


def _role() -> str:
    role = os.environ.get("FIREBRIEF_APP_ROLE", "firebrief_app")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"FIREBRIEF_APP_ROLE is not a valid identifier: {role!r}")
    return role


def upgrade() -> None:
    op.create_table(
        "budget_counters",
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("reserved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("spent", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint("reserved >= 0", name="reserved_not_negative"),
        sa.CheckConstraint("spent >= 0", name="spent_not_negative"),
        sa.PrimaryKeyConstraint(
            "scope_type", "scope_id", "period", "period_start", name="pk_budget_counters"
        ),
    )

    op.create_table(
        "budget_reservations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("keys", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.CheckConstraint("amount >= 0", name="amount_not_negative"),
        sa.CheckConstraint("state in ('pending', 'settled', 'released')", name="state_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_budget_reservations"),
        sa.UniqueConstraint("request_id", name="uq_budget_reservations_request_id"),
    )
    op.create_index(
        "ix_budget_reservations_pending",
        "budget_reservations",
        ["state", "expires_at"],
    )

    role = _role()
    for table in TABLES:
        op.execute(f'revoke all on {table} from "{role}"')
        # No DELETE: a reservation is a record of what was charged.
        op.execute(f'grant select, insert, update on {table} to "{role}"')
    # The app may only move a reservation's state; amount and keys are immutable.
    op.execute(f'grant update (state) on budget_reservations to "{role}"')


def downgrade() -> None:
    role = _role()
    for table in TABLES:
        op.execute(f'revoke all on {table} from "{role}"')
    op.drop_index("ix_budget_reservations_pending", table_name="budget_reservations")
    op.drop_table("budget_reservations")
    op.drop_table("budget_counters")
