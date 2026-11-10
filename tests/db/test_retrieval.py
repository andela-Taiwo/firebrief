from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store import ingest
from firebrief.ingest.store_embed import embed_version
from firebrief.retrieval.search import search, text_search, vector_search
from tests.db.data import RETRIEVAL_HTML
from tests.ingest.fixtures import source

TEXT_SIDE_EDITION = "2019"


@pytest.fixture
async def version_id(owner_engine: AsyncEngine) -> uuid.UUID:
    embedder = BagOfWordsEmbedder()
    async with AsyncSession(owner_engine) as session, session.begin():
        stored = await ingest(session, source(RETRIEVAL_HTML, edition=TEXT_SIDE_EDITION))
    async with AsyncSession(owner_engine) as session, session.begin():
        await embed_version(session, stored.version_id, embedder)
    return stored.version_id


async def _search(engine: AsyncEngine, query: str, **kwargs):  # type: ignore[no-untyped-def]
    async with AsyncSession(engine) as session:
        return await search(session, query, BagOfWordsEmbedder(), **kwargs)


async def test_a_distinctive_term_finds_its_section(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    results = await _search(owner_engine, "thirty metres")

    assert results
    assert results[0].heading_path.endswith("Escape routes")


async def test_partial_word_overlap_finds_its_section(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    """Partial overlap, not paraphrase: a bag-of-words embedder cannot do the latter."""
    results = await _search(owner_engine, "closing flat entrance door")

    assert results
    assert results[0].heading_path.endswith("Fire doors")


async def test_results_carry_the_evidence(owner_engine: AsyncEngine, version_id: uuid.UUID) -> None:
    result = (await _search(owner_engine, "thirty metres"))[0]

    assert result.version_id == version_id
    assert "thirty metres" in result.text
    assert result.vector_rank is not None
    assert result.text_rank is not None
    assert result.embedding_model == "bow-1024"
    assert result.document_title
    assert result.edition == TEXT_SIDE_EDITION
    assert result.source_url.startswith("https://www.gov.uk/")


async def test_an_empty_query_returns_nothing(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    assert await _search(owner_engine, "   ") == []


async def test_a_query_with_no_matches_returns_nothing_with_a_floor(
    owner_engine: AsyncEngine, version_id: uuid.UUID
) -> None:
    """The floor is explicit: the default is no floor at all (ADR 0006)."""
    assert await _search(owner_engine, "intumescent", min_similarity=0.5) == []


async def test_the_limit_is_respected(owner_engine: AsyncEngine, version_id: uuid.UUID) -> None:
    results = await _search(owner_engine, "fire door", limit=1)

    assert len(results) == 1


async def test_a_tie_is_broken_deterministically(owner_engine: AsyncEngine) -> None:
    tied = """
    <main><h1>Ties</h1>
    <h2>Notes</h2><p>Identical body.</p>
    <h2>Notes</h2><p>Identical body.</p>
    </main>
    """
    async with AsyncSession(owner_engine) as session, session.begin():
        stored = await ingest(session, source(tied))
    async with AsyncSession(owner_engine) as session, session.begin():
        await embed_version(session, stored.version_id, BagOfWordsEmbedder())

    first = await _search(owner_engine, "identical body", limit=5)
    second = await _search(owner_engine, "identical body", limit=5)

    assert len(first) == 2, "both identical chunks should be returned"
    assert [str(result.chunk_id) for result in first] == [str(result.chunk_id) for result in second]


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
        rows = await text_search(session, "thirty metres", BagOfWordsEmbedder(), limit=3)

    assert rows
    assert rows[0].heading_path.endswith("Escape routes")


async def test_a_superseded_edition_is_not_retrieved(owner_engine: AsyncEngine) -> None:
    """Two editions of the same document: only the applicable one may answer."""
    embedder = BagOfWordsEmbedder()
    async with AsyncSession(owner_engine) as session, session.begin():
        old = await ingest(
            session,
            source(RETRIEVAL_HTML, edition="2019", effective_from=date(2019, 6, 1)),
        )
    async with AsyncSession(owner_engine) as session, session.begin():
        new = await ingest(
            session,
            source(
                RETRIEVAL_HTML.replace("thirty metres", "thirty-five metres"),
                edition="2022",
                effective_from=date(2022, 1, 1),
            ),
        )
    for version in (old.version_id, new.version_id):
        async with AsyncSession(owner_engine) as session, session.begin():
            await embed_version(session, version, embedder)

    current = await _search(owner_engine, "dead ends thirty metres")
    later = await _search(owner_engine, "dead ends thirty metres", as_of=date(2023, 1, 1))
    earlier = await _search(owner_engine, "dead ends thirty metres", as_of=date(2020, 1, 1))

    assert current
    assert {result.version_id for result in current} == {new.version_id}
    assert {result.version_id for result in later} == {new.version_id}
    assert {result.version_id for result in earlier} == {old.version_id}


async def test_two_embedding_sets_do_not_duplicate_evidence(
    owner_engine: AsyncEngine,
) -> None:
    async with AsyncSession(owner_engine) as session, session.begin():
        stored = await ingest(session, source(RETRIEVAL_HTML))
    for model in ("bow-1024", "bow-b"):
        async with AsyncSession(owner_engine) as session, session.begin():
            await embed_version(session, stored.version_id, BagOfWordsEmbedder(model=model))

    results = await _search(owner_engine, "fire door FD30S")

    assert results
    assert len(results) == len({result.heading_path for result in results})
    assert len(results) == len({result.chunk_id for result in results})
    assert {result.embedding_model for result in results} == {"bow-1024"}


async def test_the_full_text_index_exists(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        definition = (
            await connection.execute(
                sa.text("select indexdef from pg_indexes where indexname = 'ix_chunks_fts'")
            )
        ).scalar_one()

    assert "to_tsvector" in definition
    assert "gin" in definition.lower()


@pytest.mark.parametrize("query", ["FD30S", "BS 5839"])
async def test_lexical_identifiers_are_found(
    owner_engine: AsyncEngine, version_id: uuid.UUID, query: str
) -> None:
    async with AsyncSession(owner_engine) as session:
        rows = await text_search(session, query, BagOfWordsEmbedder(), limit=5)

    assert rows, f"{query!r} found nothing through the keyword side"


@pytest.mark.parametrize(("limit", "candidates"), [(0, 10), (-1, 10), (10, 5)])
async def test_invalid_limits_are_refused(
    owner_engine: AsyncEngine, version_id: uuid.UUID, limit: int, candidates: int
) -> None:
    async with AsyncSession(owner_engine) as session:
        with pytest.raises(ValueError):
            await search(
                session, "fire door", BagOfWordsEmbedder(), limit=limit, candidates=candidates
            )
