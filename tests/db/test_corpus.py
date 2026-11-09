from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.db.models import DocumentVersion
from firebrief.ingest.current import select_current
from firebrief.ingest.licence import LicenceNotAccepted
from firebrief.ingest.parse import EmptyDocument
from firebrief.ingest.store import IngestResult, ingest, source_hash
from firebrief.ingest.types import SourceDocument
from tests.ingest.fixtures import FURNITURE_ONLY_HTML, GUIDANCE_HTML, REVISED_HTML, source

CORPUS_TABLES = ("documents", "document_versions", "sections")


@pytest.fixture(autouse=True)
async def empty_corpus(owner_engine: AsyncEngine) -> None:
    """TRUNCATE bypasses the append-only row triggers; each test starts clean."""
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("truncate table sections, document_versions, documents cascade")
        )


async def _ingest(engine: AsyncEngine, document: SourceDocument) -> IngestResult:
    async with AsyncSession(engine) as session, session.begin():
        return await ingest(session, document)


async def _count(engine: AsyncEngine, statement: str, **params: object) -> int:
    async with engine.connect() as connection:
        result = await connection.execute(sa.text(statement), params)
        return int(result.scalar_one())


async def test_ingesting_a_document_stores_versions_and_sections(
    owner_engine: AsyncEngine,
) -> None:
    result = await _ingest(owner_engine, source())

    assert result.created is True
    assert result.sections == 6
    assert await _count(owner_engine, "select count(*) from documents") == 1
    assert await _count(owner_engine, "select count(*) from document_versions") == 1
    assert await _count(owner_engine, "select count(*) from sections") == 6


async def test_re_ingesting_the_same_bytes_changes_nothing(owner_engine: AsyncEngine) -> None:
    first = await _ingest(owner_engine, source())
    second = await _ingest(owner_engine, source())

    assert second.created is False
    assert second.version_id == first.version_id
    assert await _count(owner_engine, "select count(*) from document_versions") == 1


async def test_a_page_furniture_change_does_not_create_a_version(
    owner_engine: AsyncEngine,
) -> None:
    """Cookie banners and CSRF tokens change the bytes, not the guidance."""
    first = await _ingest(owner_engine, source())
    second = await _ingest(owner_engine, source(FURNITURE_ONLY_HTML))

    assert second.created is False
    assert second.version_id == first.version_id
    assert await _count(owner_engine, "select count(*) from document_versions") == 1


async def test_changed_guidance_creates_a_new_version_and_keeps_the_old_one(
    owner_engine: AsyncEngine,
) -> None:
    first = await _ingest(owner_engine, source())
    second = await _ingest(owner_engine, source(REVISED_HTML))

    assert second.created is True
    assert second.version_id != first.version_id
    assert await _count(owner_engine, "select count(*) from document_versions") == 2
    assert await _count(owner_engine, "select count(*) from sections") == 12
    assert (
        await _count(
            owner_engine,
            "select count(*) from sections where version_id = :v",
            v=first.version_id,
        )
        == 6
    )


async def test_the_version_records_the_bytes_it_read(owner_engine: AsyncEngine) -> None:
    await _ingest(owner_engine, source(FURNITURE_ONLY_HTML))
    await _ingest(owner_engine, source(GUIDANCE_HTML))

    async with owner_engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    sa.text("select source_sha256, content_hash from document_versions")
                )
            )
            .mappings()
            .one()
        )

    # Same guidance, different furniture: one version, holding the bytes it
    # actually read (the first fetch) and a content hash that ignores furniture.
    assert await _count(owner_engine, "select count(*) from document_versions") == 1
    assert row["source_sha256"] == source_hash(FURNITURE_ONLY_HTML)
    assert row["content_hash"] != row["source_sha256"]


async def test_a_version_cannot_be_updated_or_deleted(owner_engine: AsyncEngine) -> None:
    await _ingest(owner_engine, source())

    for statement in (
        "update document_versions set edition = '2020'",
        "delete from document_versions",
    ):
        async with owner_engine.begin() as connection:
            with pytest.raises(DBAPIError, match="append-only"):
                await connection.execute(sa.text(statement))


async def test_a_section_cannot_be_updated_or_deleted(owner_engine: AsyncEngine) -> None:
    await _ingest(owner_engine, source())

    for statement in ("update sections set body = 'rewritten'", "delete from sections"):
        async with owner_engine.begin() as connection:
            with pytest.raises(DBAPIError, match="append-only"):
                await connection.execute(sa.text(statement))


async def test_a_documents_title_may_change_but_it_cannot_be_deleted(
    owner_engine: AsyncEngine,
) -> None:
    await _ingest(owner_engine, source())

    async with owner_engine.begin() as connection:
        await connection.execute(sa.text("update documents set title = 'Renamed'"))
    assert await _count(owner_engine, "select count(*) from documents where title = 'Renamed'") == 1

    async with owner_engine.begin() as connection:
        with pytest.raises(DBAPIError):
            await connection.execute(sa.text("delete from documents"))


async def test_a_refused_licence_stores_nothing(owner_engine: AsyncEngine) -> None:
    with pytest.raises(LicenceNotAccepted):
        await _ingest(owner_engine, replace(source(), licence="Crown copyright"))

    assert await _count(owner_engine, "select count(*) from documents") == 0


async def test_an_empty_page_stores_nothing(owner_engine: AsyncEngine) -> None:
    with pytest.raises(EmptyDocument):
        await _ingest(owner_engine, source("<main>   </main>"))

    assert await _count(owner_engine, "select count(*) from documents") == 0


@pytest.mark.parametrize("table", CORPUS_TABLES)
async def test_the_runtime_role_has_no_write_privileges(
    app_engine: AsyncEngine, table: str
) -> None:
    async with app_engine.connect() as connection:
        row = (
            (
                await connection.execute(
                    sa.text(
                        """
                    select
                        has_table_privilege(current_user, :t, 'INSERT') as ins,
                        has_table_privilege(current_user, :t, 'UPDATE') as upd,
                        has_table_privilege(current_user, :t, 'DELETE') as dele,
                        has_table_privilege(current_user, :t, 'TRUNCATE') as trunc
                    """
                    ),
                    {"t": table},
                )
            )
            .mappings()
            .one()
        )

    granted = [name for name, value in row.items() if value]
    assert not granted, f"the runtime role has {granted} on {table}"


async def test_the_runtime_role_can_read_the_corpus(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    await _ingest(owner_engine, source())

    async with app_engine.connect() as connection:
        sections = (await connection.execute(sa.text("select count(*) from sections"))).scalar_one()
    assert sections == 6


async def test_the_runtime_role_cannot_write_the_corpus(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    await _ingest(owner_engine, source())

    async with app_engine.begin() as connection:
        with pytest.raises(DBAPIError, match="permission denied"):
            await connection.execute(
                sa.text(
                    "insert into sections (id, version_id, ordinal, heading_path, heading, body) "
                    "select gen_random_uuid(), id, 99, 'x', 'x', 'x' from document_versions"
                )
            )


def _version(edition: str, effective_from: date | None, fetched_at: datetime) -> DocumentVersion:
    return DocumentVersion(
        document_id=uuid4(),
        content_hash=edition,
        source_sha256=edition,
        fetched_at=fetched_at,
        licence="ogl-3.0",
        edition=edition,
        effective_from=effective_from,
    )


def test_the_current_version_is_the_latest_applicable() -> None:
    old = _version("2019", date(2019, 6, 1), datetime(2026, 1, 1, tzinfo=UTC))
    new = _version("2022", date(2022, 1, 1), datetime(2026, 2, 1, tzinfo=UTC))

    assert select_current([old, new], as_of=date(2021, 1, 1)) is old
    assert select_current([old, new], as_of=date(2023, 1, 1)) is new
    assert select_current([new], as_of=date(2020, 1, 1)) is None


def test_a_later_fetch_wins_when_the_edition_is_the_same() -> None:
    first = _version("2019", date(2019, 6, 1), datetime(2026, 1, 1, tzinfo=UTC))
    correction = _version("2019", date(2019, 6, 1), datetime(2026, 3, 1, tzinfo=UTC))

    assert select_current([first, correction], as_of=date(2023, 1, 1)) is correction
