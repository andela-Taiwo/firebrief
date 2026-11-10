"""Hybrid retrieval: meaning and keywords, fused by rank.

Fire guidance mixes both kinds of query. "How wide can a dead end be?" is semantic;
"BS 5839" is lexical. Full-text search finds the second, vectors find the first, and
Reciprocal Rank Fusion combines them without inventing a weight for either.

Exact cosine search over `double precision[]` — see ADR 0005 for why there is no
pgvector index yet.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.ingest.embed import Embedder
from firebrief.retrieval.types import Retrieved

RRF_K = 60
CANDIDATES = 50

VECTOR_SQL = sa.text(
    """
    select ranked.* from (
        select c.id as chunk_id, c.section_id, c.version_id, c.heading_path, c.text,
               (
                   sum(c.embedding[q.i::int] * q.v)
                   / nullif(
                       sqrt(sum(c.embedding[q.i::int] * c.embedding[q.i::int]))
                       * sqrt(sum(q.v * q.v)), 0
                     )
               ) as similarity
        from chunks c
        cross join unnest(cast(:vec as double precision[])) with ordinality as q(v, i)
        where c.embedding_model = :model and c.dimensions = :dims
        group by c.id
    ) ranked
    where ranked.similarity >= :min_similarity
    order by ranked.similarity desc nulls last, ranked.chunk_id
    limit :limit
    """
)

TEXT_SQL = sa.text(
    """
    select c.id as chunk_id, c.section_id, c.version_id, c.heading_path, c.text,
           ts_rank_cd(
               to_tsvector('english', c.heading_path || ' ' || c.text),
               websearch_to_tsquery('english', :q)
           ) as rank
    from chunks c
    where to_tsvector('english', c.heading_path || ' ' || c.text)
          @@ websearch_to_tsquery('english', :q)
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
    min_similarity: float = 0.1,
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
            "dims": embedder.dimensions,
            "limit": limit,
            "min_similarity": min_similarity,
        },
    )


async def text_search(
    session: AsyncSession, query: str, *, limit: int = CANDIDATES
) -> list[sa.Row[tuple[object, ...]]]:
    """The keyword half, exposed so it can be tested on its own."""
    if not query.strip():
        return []
    return await _run(session, TEXT_SQL, {"q": query, "limit": limit})


async def search(
    session: AsyncSession,
    query: str,
    embedder: Embedder,
    *,
    limit: int = 10,
    candidates: int = CANDIDATES,
    k: int = RRF_K,
    min_similarity: float = 0.1,
) -> list[Retrieved]:
    if not query.strip():
        return []
    if limit <= 0:
        raise ValueError("limit must be positive")

    vector_rows = await vector_search(
        session, query, embedder, limit=candidates, min_similarity=min_similarity
    )
    text_rows = await text_search(session, query, limit=candidates)

    vector_ids = [row.chunk_id for row in vector_rows]
    text_ids = [row.chunk_id for row in text_rows]
    vector_rank = {chunk_id: rank for rank, chunk_id in enumerate(vector_ids, start=1)}
    text_rank = {chunk_id: rank for rank, chunk_id in enumerate(text_ids, start=1)}

    scores = fuse(vector_ids, text_ids, k=k)
    rows = {row.chunk_id: row for row in (*vector_rows, *text_rows)}

    ordered = sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))[:limit]
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
        )
        for chunk_id, score in ordered
    ]
