"""Recall@3 on the checked-in retrieval set.

A smoke test for the plumbing: six questions, three sections, a bag-of-words
embedder. It proves retrieval works end to end; it does not prove retrieval is
*good*. The real quality gate runs against the real corpus with a real embedder.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store import ingest
from firebrief.ingest.store_embed import embed_version
from firebrief.retrieval.search import search
from tests.db.data import RETRIEVAL_HTML
from tests.ingest.fixtures import source

QUERIES = Path(__file__).resolve().parents[2] / "evals" / "retrieval" / "queries.toml"
MIN_RECALL = 0.8


async def test_recall_at_three_meets_the_floor(owner_engine: AsyncEngine) -> None:
    embedder = BagOfWordsEmbedder()
    async with AsyncSession(owner_engine) as session, session.begin():
        stored = await ingest(session, source(RETRIEVAL_HTML))
    async with AsyncSession(owner_engine) as session, session.begin():
        await embed_version(session, stored.version_id, embedder)

    cases = tomllib.loads(QUERIES.read_text())["queries"]
    hits = 0
    misses: list[str] = []

    async with AsyncSession(owner_engine) as session:
        for case in cases:
            results = await search(session, case["question"], embedder, limit=3)
            paths = [result.heading_path for result in results]
            if any(path.split(" > ")[-1] == case["expected"] for path in paths):
                hits += 1
            else:
                misses.append(f"{case['question']} -> {paths}")

    recall = hits / len(cases)
    print(f"recall@3 = {recall:.2f} ({hits}/{len(cases)})")
    assert recall >= MIN_RECALL, f"recall {recall:.2f} below {MIN_RECALL}; misses: {misses}"
