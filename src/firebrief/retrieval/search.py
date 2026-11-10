"""Hybrid retrieval: meaning and keywords, fused by rank.

Both sides are restricted to the version of each document that is in force on the
date asked about, using the same rule as `select_current`: latest `effective_from`
that has arrived, then latest `fetched_at`. Without that, a superseded edition
competes with the current one and answers cite guidance that no longer applies.

Both sides are also restricted to one embedding model and one chunker
configuration, so two embedded sets cannot fill the results with duplicates.

Exact cosine search over `double precision[]` — see ADR 0005.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.ingest.chunk import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunker_id
from firebrief.ingest.embed import Embedder
from firebrief.retrieval.types import Retrieved

RRF_K = 60
CANDIDATES = 50
DEFAULT_CHUNKER = chunker_id(DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS)

_CURRENT = """
with applicable as (
    select distinct on (document_id) id
    from document_versions
    where effective_from is null or effective_from <= :as_of
    order by document_id, effective_from desc nulls last, fetched_at desc
)
"""

VECTOR_SQL = sa.text(
    _CURRENT  # noqa: S608 - constant SQL, no interpolation
    + """
    , sim as (
        select c.id as chunk_id,
               (
                   sum(c.embedding[q.i::int] * q.v)
                   / nullif(
                       sqrt(sum(c.embedding[q.i::int] * c.embedding[q.i::int]))
                       * sqrt(sum(q.v * q.v)), 0
                     )
               ) as similarity
        from chunks c
        cross join unnest(cast(:vec as double precision[])) with ordinality as q(v, i)
        where c.embedding_model = :model
          and c.chunker = :chunker
          and c.dimensions = :dims
          and c.version_id in (select id from applicable)
        group by c.id
    )
    select c.id as chunk_id, c.section_id, c.version_id, c.heading_path, c.text,
           c.embedding_model, d.title as document_title, v.edition, d.source_url,
           sim.similarity
    from sim
    join chunks c on c.id = sim.chunk_id
    join document_versions v on v.id = c.version_id
    join documents d on d.id = v.document_id
    where sim.similarity >= :min_similarity
    order by sim.similarity desc nulls last, c.id
    limit :limit
    """
)

TEXT_SQL = sa.text(
    _CURRENT  # noqa: S608 - constant SQL, no interpolation
    + """
    select c.id as chunk_id, c.section_id, c.version_id, c.heading_path, c.text,
           c.embedding_model, d.title as document_title, v.edition, d.source_url,
           ts_rank_cd(
               to_tsvector('english', c.heading_path || ' ' || c.text),
               websearch_to_tsquery('english', :q)
           ) as rank
    from chunks c
    join document_versions v on v.id = c.version_id
    join documents d on d.id = v.document_id
    where to_tsvector('english', c.heading_path || ' ' || c.text)
          @@ websearch_to_tsquery('english', :q)
      and c.embedding_model = :model
      and c.chunker = :chunker
      and c.version_id in (select id from applicable)
    order by rank desc, c.id
    limit :limit
    """
)


def fuse(
    vector_ids: Sequence[uuid.UUID], text_ids: Sequence[uuid.UUID], *, k: int = RRF_K
) -> dict[uuid.UUID, float]:
    """Reciprocal Rank Fusion: 1/(k + rank) from each side, summed."""
    scores: dict[uuid.UUID, float] = {}
    for ids in (vector_ids, text_ids):
        for rank, chunk_id in enumerate(ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def order(scores: dict[uuid.UUID, float]) -> list[uuid.UUID]:
    """Rank by fused score, breaking ties by chunk id so results are stable."""
    return [
        chunk_id
        for chunk_id, _ in sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))
    ]


def _as_of(value: date | None) -> date:
    return value or datetime.now(UTC).date()


async def _run(
    session: AsyncSession, statement: sa.TextClause, params: dict[str, object]
) -> list[sa.Row[tuple[object, ...]]]:
    return list((await session.execute(statement, params)).all())


async def vector_search(
    session: AsyncSession,
    query: str,
    embedder: Embedder,
    *,
    limit: int = CANDIDATES,
    as_of: date | None = None,
    chunker: str = DEFAULT_CHUNKER,
    min_similarity: float | None = None,
) -> list[sa.Row[tuple[object, ...]]]:
    """The meaning-based half, exposed so it can be tested on its own."""
    if not query.strip():
        return []
    vector = (await embedder.embed([query]))[0]
    return await _run(
        session,
        VECTOR_SQL,
        {
            "vec": vector,
            "model": embedder.model,
            "chunker": chunker,
            "dims": embedder.dimensions,
            "limit": limit,
            "as_of": _as_of(as_of),
            "min_similarity": -1.0 if min_similarity is None else min_similarity,
        },
    )


async def text_search(
    session: AsyncSession,
    query: str,
    embedder: Embedder,
    *,
    limit: int = CANDIDATES,
    as_of: date | None = None,
    chunker: str = DEFAULT_CHUNKER,
) -> list[sa.Row[tuple[object, ...]]]:
    """The keyword half, exposed so it can be tested on its own."""
    if not query.strip():
        return []
    return await _run(
        session,
        TEXT_SQL,
        {
            "q": query,
            "model": embedder.model,
            "chunker": chunker,
            "limit": limit,
            "as_of": _as_of(as_of),
        },
    )


async def search(
    session: AsyncSession,
    query: str,
    embedder: Embedder,
    *,
    limit: int = 10,
    candidates: int = CANDIDATES,
    k: int = RRF_K,
    as_of: date | None = None,
    chunker: str = DEFAULT_CHUNKER,
    min_similarity: float | None = None,
) -> list[Retrieved]:
    if not query.strip():
        return []
    if limit <= 0:
        raise ValueError("limit must be positive")
    if candidates < limit:
        raise ValueError("candidates must be at least limit, or fusion silently truncates")

    vector_rows = await vector_search(
        session,
        query,
        embedder,
        limit=candidates,
        as_of=as_of,
        chunker=chunker,
        min_similarity=min_similarity,
    )
    text_rows = await text_search(
        session, query, embedder, limit=candidates, as_of=as_of, chunker=chunker
    )

    vector_ids = [row.chunk_id for row in vector_rows]
    text_ids = [row.chunk_id for row in text_rows]
    vector_rank = {chunk_id: rank for rank, chunk_id in enumerate(vector_ids, start=1)}
    text_rank = {chunk_id: rank for rank, chunk_id in enumerate(text_ids, start=1)}

    scores = fuse(vector_ids, text_ids, k=k)
    rows = {row.chunk_id: row for row in (*vector_rows, *text_rows)}

    ordered = [(chunk_id, scores[chunk_id]) for chunk_id in order(scores)[:limit]]
    return [
        Retrieved(
            chunk_id=chunk_id,
            section_id=rows[chunk_id].section_id,
            version_id=rows[chunk_id].version_id,
            heading_path=rows[chunk_id].heading_path,
            text=rows[chunk_id].text,
            score=score,
            vector_rank=vector_rank.get(chunk_id),
            text_rank=text_rank.get(chunk_id),
            embedding_model=rows[chunk_id].embedding_model,
            document_title=rows[chunk_id].document_title,
            edition=rows[chunk_id].edition,
            source_url=rows[chunk_id].source_url,
        )
        for chunk_id, score in ordered
    ]
