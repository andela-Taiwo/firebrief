"""chunks: embedded pieces of an immutable version

Embeddings are stored as double precision arrays and searched exactly. ADR 0005
records why pgvector is not used yet, and when to reconsider.

Revision ID: 0007_chunks
Revises: 0006_corpus
Create Date: 2026-11-09
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_chunks"
down_revision: str | None = "0006_corpus"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role() -> str:
    role = os.environ.get("FIREBRIEF_APP_ROLE", "firebrief_app")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"FIREBRIEF_APP_ROLE is not a valid identifier: {role!r}")
    return role


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            name=op.f("fk_chunks_version_id_document_versions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint(
            "version_id", "embedding_model", "ordinal", name="uq_chunks_version_model_ordinal"
        ),
    )
    op.create_index(op.f("ix_chunks_version_id"), "chunks", ["version_id"], unique=False)

    # Chunks are derived, but they are derived from an immutable version and a
    # citation may point at one. Same guards as the rest of the corpus.
    for table in ("chunks",):
        op.execute(
            f"create trigger {table}_append_only before update or delete on {table} "
            "for each row execute function forbid_mutation()"
        )
        op.execute(
            f"create trigger {table}_no_truncate before truncate on {table} "
            "for each statement execute function forbid_truncate()"
        )

    role = _role()
    op.execute(f'revoke all on chunks from "{role}"')
    op.execute(f'grant select on chunks to "{role}"')


def downgrade() -> None:
    role = _role()
    op.execute(f'revoke all on chunks from "{role}"')
    op.execute("drop trigger chunks_no_truncate on chunks")
    op.execute("drop trigger chunks_append_only on chunks")
    op.drop_index(op.f("ix_chunks_version_id"), table_name="chunks")
    op.drop_table("chunks")
