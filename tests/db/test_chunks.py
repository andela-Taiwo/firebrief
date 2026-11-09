from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.ingest.embed import FakeEmbedder
from firebrief.ingest.store import ingest
from firebrief.ingest.store_embed import VersionNotFound, embed_version
from tests.ingest.fixtures import source


@pytest.fixture(autouse=True)
async def empty_corpus(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("select set_config('session_replication_role', 'replica', true)")
        )
        await connection.execute(
            sa.text("truncate table chunks, sections, document_versions, documents cascade")
        )


async def _stored_version(engine: AsyncEngine) -> uuid.UUID:
    async with AsyncSession(engine) as session, session.begin():
        return (await ingest(session, source())).version_id


async def _embed(engine: AsyncEngine, version_id: uuid.UUID, embedder=None) -> int:  # type: ignore[no-untyped-def]
    async with AsyncSession(engine) as session, session.begin():
        return await embed_version(session, version_id, embedder or FakeEmbedder())


async def _count(engine: AsyncEngine, statement: str, **params: object) -> int:
    async with engine.connect() as connection:
        return int((await connection.execute(sa.text(statement), params)).scalar_one())


async def test_every_section_becomes_a_chunk(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    assert await _embed(owner_engine, version_id) == 6
    assert await _count(owner_engine, "select count(*) from chunks") == 6
    assert (
        await _count(
            owner_engine,
            "select count(*) from chunks where heading_path = :p",
            p="Fire safety in purpose-built flats > Means of escape",
        )
        == 1
    )


async def test_re_embedding_adds_nothing(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    await _embed(owner_engine, version_id)
    await _embed(owner_engine, version_id)

    assert await _count(owner_engine, "select count(*) from chunks") == 6


async def test_a_second_model_adds_a_second_set(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    await _embed(owner_engine, version_id, FakeEmbedder(model="fake-embed-1"))
    await _embed(owner_engine, version_id, FakeEmbedder(model="fake-embed-2"))

    assert await _count(owner_engine, "select count(*) from chunks") == 12
    assert (
        await _count(
            owner_engine,
            "select count(*) from chunks where embedding_model = :m",
            m="fake-embed-1",
        )
        == 6
    )


async def test_an_unknown_version_is_refused(owner_engine: AsyncEngine) -> None:
    with pytest.raises(VersionNotFound):
        await _embed(owner_engine, uuid.uuid4())


async def test_chunks_are_append_only(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)
    await _embed(owner_engine, version_id)

    for statement in ("update chunks set text = 'rewritten'", "delete from chunks"):
        async with owner_engine.begin() as connection:
            with pytest.raises(DBAPIError, match="append-only"):
                await connection.execute(sa.text(statement))


async def test_the_runtime_role_can_read_chunks_but_not_write_them(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    version_id = await _stored_version(owner_engine)
    await _embed(owner_engine, version_id)

    async with app_engine.connect() as connection:
        assert (await connection.execute(sa.text("select count(*) from chunks"))).scalar_one() == 6

    async with app_engine.begin() as connection:
        with pytest.raises(DBAPIError, match="permission denied"):
            await connection.execute(
                sa.text(
                    "insert into chunks (id, version_id, embedding_model, ordinal, heading_path, "
                    "text, token_estimate, embedding) select gen_random_uuid(), id, 'x', 99, "
                    "'x', 'x', 1, array[0.1, 0.2] from document_versions"
                )
            )
