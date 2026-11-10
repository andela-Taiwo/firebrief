from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store import ingest
from firebrief.ingest.store_embed import embed_version
from firebrief.ingest.types import SourceDocument
from firebrief.retrieval.search import search, text_search, vector_search
from tests.ingest.fixtures import source

CORPUS_HTML = """
<main>
<h1>Fire safety in flats</h1>
<h2>Fire doors</h2>
<p>Flat entrance doors must be self-closing and fire-resisting.</p>
<h2>Signage</h2>
<p>Fire door signs must be visible and never obstructed.</p>
<h2>Escape routes</h2>
<p>Dead ends must be limited in length to thirty metres.</p>
</main>
"""


@pytest.fixture(autouse=True)
async def empty_corpus(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("select set_config('session_replication_role', 'replica', true)")
        )
        await connection.execute(
            sa.text("truncate table chunks, sections, document_versions, documents cascade")
        )


@pytest.fixture
async def version_id(owner_engine: AsyncEngine) -> uuid.UUID:
    document: SourceDocument = source(CORPUS_HTML)
    async with AsyncSession(owner_engine) as session, session.begin():
        result = await ingest(session, document)
    async with AsyncSession(owner_engine) as session, session.begin():
        await embed_version(session, result.version_id, BagOfWordsEmbedder())
    return result.version_id


async def _search(engine: AsyncEngine, query: str, *, limit: int = 10):
    async with AsyncSession(engine) as session:
        return await search(session, query, BagOfWordsEmbedder(), limit=limit)


async def test_a_distinctive_term_finds_its_section(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    results = await _search(owner_engine, "thirty metres")

    assert results
    assert results[0].heading_path.endswith("Escape routes")


async def test_a_paraphrase_finds_its_section(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    results = await _search(owner_engine, "closing flat entrance door")

    assert results
    assert results[0].heading_path.endswith("Fire doors")


async def test_results_carry_the_evidence(owner_engine: AsyncEngine, version_id: uuid.UUID) -> None:
    result = (await _search(owner_engine, "thirty metres"))[0]

    assert result.version_id == version_id
    assert result.section_id is not None
    assert "thirty metres" in result.text
    assert result.vector_rank is not None
    assert result.text_rank is not None


async def test_an_empty_query_returns_nothing(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    assert await _search(owner_engine, "   ") == []


async def test_a_query_with_no_matches_returns_nothing(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    assert await _search(owner_engine, "intumescent") == []


async def test_the_limit_is_respected(owner_engine: AsyncEngine, version_id: uuid.UUID) -> None:
    results = await _search(owner_engine, "fire door", limit=1)

    assert len(results) == 1


async def test_ordering_is_deterministic(owner_engine: AsyncEngine, version_id: uuid.UUID) -> None:
    first = await _search(owner_engine, "fire door")
    second = await _search(owner_engine, "fire door")

    assert [result.chunk_id for result in first] == [result.chunk_id for result in second]


async def test_the_vector_side_finds_a_chunk_on_its_own(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    async with AsyncSession(owner_engine) as session:
        rows = await vector_search(
            session, "closing flat entrance door", BagOfWordsEmbedder(), limit=3
        )

    assert rows
    assert rows[0].heading_path.endswith("Fire doors")


async def test_the_keyword_side_finds_a_chunk_on_its_own(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    async with AsyncSession(owner_engine) as session:
        rows = await text_search(session, "thirty metres", limit=3)

    assert rows
    assert rows[0].heading_path.endswith("Escape routes")
