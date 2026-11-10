"""Recall@k on the checked-in retrieval evaluation set.

This is a quality gate, not a unit test: it says how often the right section is in
the top three, and fails if that drops below the agreed floor.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store import ingest
from firebrief.ingest.store_embed import embed_version
from firebrief.retrieval.search import search
from tests.ingest.fixtures import source

QUERIES = Path(__file__).resolve().parents[2] / "evals" / "retrieval" / "queries.toml"
MIN_RECALL = 0.8

CORPUS_HTML = """
<main><h1>Fire safety in flats</h1>
<h2>Fire doors</h2><p>Flat entrance doors must be self-closing and fire-resisting.</p>
<h2>Signage</h2><p>Fire door signs must be visible and never obstructed.</p>
<h2>Escape routes</h2><p>Dead ends must be limited in length to thirty metres.</p>
</main>
"""


async def test_recall_at_three_meets_the_floor(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as connection:
        await connection.execute(
            sa.text("select set_config('session_replication_role', 'replica', true)")
        )
        await connection.execute(
            sa.text("truncate table chunks, sections, document_versions, documents cascade")
        )

    embedder = BagOfWordsEmbedder()
    async with AsyncSession(owner_engine) as session, session.begin():
        stored = await ingest(session, source(CORPUS_HTML))
    async with AsyncSession(owner_engine) as session, session.begin():
        await embed_version(session, stored.version_id, embedder)

    cases = tomllib.loads(QUERIES.read_text())["queries"]
    hits = 0
    misses: list[str] = []

    async with AsyncSession(owner_engine) as session:
        for case in cases:
            results = await search(session, case["question"], embedder, limit=3)
            paths = [result.heading_path for result in results]
            if any(path.endswith(case["expected"]) for path in paths):
                hits += 1
            else:
                misses.append(f"{case['question']} -> {paths}")

    recall = hits / len(cases)
    print(f"recall@3 = {recall:.2f} ({hits}/{len(cases)})")
    assert recall >= MIN_RECALL, f"recall {recall:.2f} below {MIN_RECALL}; misses: {misses}"
