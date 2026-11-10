"""full-text index for hybrid retrieval

Revision ID: 0008_retrieval_index
Revises: 0007_chunks
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_retrieval_index"
down_revision: str | None = "0007_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "create index ix_chunks_fts on chunks using gin "
        "(to_tsvector('english', heading_path || ' ' || text))"
    )


def downgrade() -> None:
    op.execute("drop index ix_chunks_fts")
