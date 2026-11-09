from __future__ import annotations

from dataclasses import replace

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.ingest.licence import LicenceNotAccepted
from firebrief.ingest.parse import EmptyDocument
from firebrief.ingest.store import IngestResult, ingest
from firebrief.ingest.types import SourceDocument
from tests.ingest.fixtures import REVISED_HTML, source


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
    assert result.sections == 4
    assert await _count(owner_engine, "select count(*) from documents") == 1
    assert await _count(owner_engine, "select count(*) from document_versions") == 1
    assert await _count(owner_engine, "select count(*) from sections") == 4


async def test_re_ingesting_the_same_bytes_changes_nothing(owner_engine: AsyncEngine) -> None:
    first = await _ingest(owner_engine, source())
    second = await _ingest(owner_engine, source())

    assert second.created is False
    assert second.version_id == first.version_id
    assert await _count(owner_engine, "select count(*) from document_versions") == 1
    assert await _count(owner_engine, "select count(*) from sections") == 4


async def test_changed_bytes_create_a_new_version_and_keep_the_old_one(
    owner_engine: AsyncEngine,
) -> None:
    first = await _ingest(owner_engine, source())
    second = await _ingest(owner_engine, source(REVISED_HTML))

    assert second.created is True
    assert second.version_id != first.version_id
    assert await _count(owner_engine, "select count(*) from document_versions") == 2
    # Both versions keep their own sections; nothing was rewritten.
    assert await _count(owner_engine, "select count(*) from sections") == 8
    old_body = await _count(
        owner_engine,
        "select count(*) from sections where version_id = :v",
        v=first.version_id,
    )
    assert old_body == 4


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


async def test_a_refused_licence_stores_nothing(owner_engine: AsyncEngine) -> None:
    refused = replace(source(), licence="Crown copyright")

    with pytest.raises(LicenceNotAccepted):
        await _ingest(owner_engine, refused)

    assert await _count(owner_engine, "select count(*) from documents") == 0


async def test_a_page_with_no_sections_stores_nothing(owner_engine: AsyncEngine) -> None:
    with pytest.raises(EmptyDocument):
        await _ingest(owner_engine, source("<html><body><p>Nothing.</p></body></html>"))

    assert await _count(owner_engine, "select count(*) from documents") == 0


async def test_the_runtime_role_can_read_the_corpus_but_not_write_it(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await _ingest(owner_engine, source())

    async with app_engine.connect() as connection:
        sections = (await connection.execute(sa.text("select count(*) from sections"))).scalar_one()
    assert sections == 4

    async with app_engine.begin() as connection:
        with pytest.raises(DBAPIError):
            await connection.execute(
                sa.text(
                    "insert into sections (id, version_id, ordinal, heading_path, heading, body) "
                    "values (gen_random_uuid(), gen_random_uuid(), 99, 'x', 'x', 'x')"
                )
            )
