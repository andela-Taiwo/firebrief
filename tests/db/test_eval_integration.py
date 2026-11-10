from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.answer import FixedJudge, answer_question
from firebrief.eval import ExtractiveProvider, load_cases, run_suite
from firebrief.eval.types import Expect
from firebrief.ingest import SourceDocument, ingest
from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store_embed import embed_version

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evals" / "answering" / "corpus.html"
CASES = ROOT / "evals" / "answering" / "questions.toml"


async def test_the_baseline_is_measured_end_to_end(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
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
    async with AsyncSession(owner_engine) as session, session.begin():
        stored = await ingest(session, document)
    async with AsyncSession(owner_engine) as session, session.begin():
        await embed_version(session, stored.version_id, embedder)

    provider = ExtractiveProvider()
    async with AsyncSession(app_engine) as session:

        async def answer(question: str):  # type: ignore[no-untyped-def]
            return await answer_question(
                session, question, embedder=embedder, provider=provider, judge=FixedJudge()
            )

        report = await run_suite(load_cases(CASES), answer)

    assert report.total == len(load_cases(CASES))
    assert report.citation_precision == pytest.approx(1.0)
    # The baseline always quotes something, so it cannot refuse: that is the point of it.
    assert {outcome.case.id for outcome in report.failures} == {
        "no-answer-colour",
        "no-answer-cost",
    }
    assert report.refusal_accuracy == pytest.approx(0.0)
    assert report.answer_accuracy == pytest.approx(1.0)
    assert all(o.case.expect is Expect.ANSWER for o in report.outcomes if o.correct)
