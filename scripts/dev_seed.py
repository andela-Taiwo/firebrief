#!/usr/bin/env python3
"""Create the local development workspace, user and corpus.

Idempotent: running it twice does not duplicate anything.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from firebrief.api.dev import DEV_EMAIL, DEV_TENANT, DEV_USER
from firebrief.db.session import tenant_session
from firebrief.ingest import SourceDocument, ingest
from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store_embed import embed_version

ROOT = Path(__file__).resolve().parents[1]


def owner_url() -> str:
    """Seeding creates a tenant, which is a privileged onboarding action."""
    return os.environ.get(
        "FIREBRIEF_OWNER_DATABASE_URL",
        "postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_test",
    )


CORPUS = ROOT / "config" / "dev-corpus.html"


async def main() -> None:
    engine = create_async_engine(owner_url())
    tenant_id = uuid.UUID(DEV_TENANT)

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(
                "insert into tenants (id, name) values (:id, 'Local development') "
                "on conflict (id) do nothing"
            ),
            {"id": DEV_TENANT},
        )

    async with tenant_session(engine, tenant_id) as session:
        await session.execute(
            sa.text(
                "insert into users (id, tenant_id, email, name) "
                "values (:id, :tenant_id, :email, 'Local developer') "
                "on conflict (id) do nothing"
            ),
            {"id": DEV_USER, "tenant_id": DEV_TENANT, "email": DEV_EMAIL},
        )
        await session.execute(
            sa.text(
                "insert into memberships (id, tenant_id, user_id, role) "
                "values (:id, :tenant_id, :user_id, 'owner') on conflict do nothing"
            ),
            {
                "id": "018f0000-0000-7000-8000-0000000000ac",
                "tenant_id": DEV_TENANT,
                "user_id": DEV_USER,
            },
        )

    document = SourceDocument(
        slug="dev-corpus",
        title="Fire safety in flats: demonstration sample",
        source_url="https://example.invalid/dev-corpus",
        html=CORPUS.read_text(),
        licence="OGL-3.0",
        edition="2019",
        fetched_at=datetime.now(UTC),
        effective_from=date(2019, 6, 1),
    )

    async with tenant_session(engine, tenant_id) as session:
        stored = await ingest(session, document)
    async with tenant_session(engine, tenant_id) as session:
        await embed_version(session, stored.version_id, BagOfWordsEmbedder())

    await engine.dispose()
    print(f"workspace: {DEV_TENANT}")
    print(f"email:     {DEV_EMAIL}")
    print(f"sign in:   http://127.0.0.1:5173/sign-in?tenant={DEV_TENANT}")


if __name__ == "__main__":
    asyncio.run(main())
