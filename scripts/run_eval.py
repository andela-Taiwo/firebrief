#!/usr/bin/env python3
"""Run the answer evaluation and print a table.

Default provider is the extractive baseline: deterministic, no key, no cost. It is the
floor a real model has to beat.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from firebrief.answer import FixedJudge, answer_question
from firebrief.eval import ExtractiveProvider, load_cases, run_suite
from firebrief.ingest import SourceDocument, ingest
from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store_embed import embed_version

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "evals" / "answering" / "corpus.html"
CASES = ROOT / "evals" / "answering" / "questions.toml"
DEFAULT_URL = "postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_test"


async def run(threshold: float) -> int:
    engine = create_async_engine(os.environ.get("DATABASE_URL", DEFAULT_URL))
    embedder = BagOfWordsEmbedder()
    document = SourceDocument(
        slug="eval-fixture-corpus",
        title="Fire safety in flats",
        source_url="https://www.gov.uk/eval-fixture",
        html=CORPUS.read_text(),
        licence="OGL-3.0",
        edition="2019",
        fetched_at=datetime.now(UTC),
        effective_from=date(2019, 6, 1),
    )
    try:
        async with AsyncSession(engine) as session, session.begin():
            stored = await ingest(session, document)
        async with AsyncSession(engine) as session, session.begin():
            await embed_version(session, stored.version_id, embedder)

        provider = ExtractiveProvider()
        judge = FixedJudge()

        async with AsyncSession(engine) as session:

            async def answer(question: str):  # type: ignore[no-untyped-def]
                return await answer_question(
                    session,
                    question,
                    embedder=embedder,
                    provider=provider,
                    judge=judge,
                )

            report = await run_suite(load_cases(CASES), answer)
    finally:
        await engine.dispose()

    print(report.table())
    print()
    print(report.summary())
    return 0 if report.accuracy >= threshold else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args(argv)
    return asyncio.run(run(args.threshold))


if __name__ == "__main__":
    raise SystemExit(main())
