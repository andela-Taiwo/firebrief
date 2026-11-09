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

LONG_HTML = (
    "<main><h1>Long document</h1><h2>Section</h2><p>"
    + " ".join(f"word{index}" for index in range(600))
    + "</p></main>"
)


class ShortEmbedder:
    model = "short"
    dimensions = 8

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return [[0.0] * 8 for _ in texts[:-1]]


class WrongDimensionsEmbedder:
    model = "wrong-dims"
    dimensions = 8

    async def embed(self, texts):  # type: ignore[no-untyped-def]
        return [[0.0] * 4 for _ in texts]


@pytest.fixture(autouse=True)
async def empty_corpus(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("select set_config('session_replication_role', 'replica', true)")
        )
        await connection.execute(
            sa.text("truncate table chunks, sections, document_versions, documents cascade")
        )


async def _stored_version(engine: AsyncEngine, html: str | None = None) -> uuid.UUID:
    async with AsyncSession(engine) as session, session.begin():
        document = source() if html is None else source(html)
        return (await ingest(session, document)).version_id


async def _embed(engine: AsyncEngine, version_id: uuid.UUID, embedder=None, **kwargs):  # type: ignore[no-untyped-def]
    async with AsyncSession(engine) as session, session.begin():
        return await embed_version(session, version_id, embedder or FakeEmbedder(), **kwargs)


async def _count(engine: AsyncEngine, statement: str, **params: object) -> int:
    async with engine.connect() as connection:
        return int((await connection.execute(sa.text(statement), params)).scalar_one())


async def test_every_section_becomes_a_chunk(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    result = await _embed(owner_engine, version_id)

    assert result.created == 6
    assert result.existing == 0
    assert await _count(owner_engine, "select count(*) from chunks") == 6


async def test_chunks_resolve_to_their_own_section(owner_engine: AsyncEngine) -> None:
    """The fixture has two sections called "Notes"; heading_path cannot tell them apart."""
    version_id = await _stored_version(owner_engine)
    await _embed(owner_engine, version_id)

    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                sa.text(
                    "select section_id, text from chunks where heading_path like :p "
                    "order by ordinal"
                ),
                {"p": "%Notes"},
            )
        ).all()

    assert len(rows) == 2
    first_id, first_text = rows[0]
    second_id, second_text = rows[1]
    assert first_id != second_id
    assert first_text == "First note."
    assert second_text == "Second note."


async def test_re_embedding_reports_nothing_created(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    first = await _embed(owner_engine, version_id)
    second = await _embed(owner_engine, version_id)

    assert first.created == 6
    assert second.created == 0
    assert second.existing == 6
    assert await _count(owner_engine, "select count(*) from chunks") == 6


async def test_a_second_model_adds_a_second_set(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    await _embed(owner_engine, version_id, FakeEmbedder(model="fake-embed-1"))
    second = await _embed(owner_engine, version_id, FakeEmbedder(model="fake-embed-2"))

    assert second.created == 6
    assert await _count(owner_engine, "select count(*) from chunks") == 12


async def test_a_different_chunker_produces_a_separate_complete_set(
    owner_engine: AsyncEngine,
) -> None:
    version_id = await _stored_version(owner_engine)

    await _embed(owner_engine, version_id, max_tokens=300, overlap_tokens=50)
    second = await _embed(owner_engine, version_id, max_tokens=100, overlap_tokens=20)

    assert second.created == 6
    assert await _count(owner_engine, "select count(*) from chunks") == 12
    assert await _count(owner_engine, "select count(distinct chunker) from chunks") == 2


async def test_a_long_section_splits_end_to_end(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine, LONG_HTML)

    result = await _embed(owner_engine, version_id, max_tokens=60, overlap_tokens=10)

    assert result.created > 1
    assert await _count(owner_engine, "select count(distinct section_id) from chunks") == 1
    assert await _count(owner_engine, "select count(*) from chunks where token_estimate > 60") == 0


async def test_a_wrong_vector_count_is_refused(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    with pytest.raises(ValueError, match="expected 6 vectors"):
        await _embed(owner_engine, version_id, ShortEmbedder())

    assert await _count(owner_engine, "select count(*) from chunks") == 0


async def test_a_dimension_mismatch_is_refused(owner_engine: AsyncEngine) -> None:
    version_id = await _stored_version(owner_engine)

    with pytest.raises(ValueError, match="expected 8 dimensions"):
        await _embed(owner_engine, version_id, WrongDimensionsEmbedder())

    assert await _count(owner_engine, "select count(*) from chunks") == 0


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
                    "insert into chunks (id, version_id, section_id, embedding_model, chunker, "
                    "ordinal, heading_path, text, char_start, char_end, token_estimate, "
                    "dimensions, embedding) select gen_random_uuid(), c.version_id, c.section_id, "
                    "'x', 'x', 99, 'x', 'x', 0, 1, 1, 2, array[0.1, 0.2] from chunks c limit 1"
                )
            )
