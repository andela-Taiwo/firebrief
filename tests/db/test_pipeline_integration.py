from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.answer import FixedJudge, RefusalReason, answer_question
from firebrief.ingest.embed import BagOfWordsEmbedder
from firebrief.ingest.store import ingest
from firebrief.ingest.store_embed import embed_version
from firebrief.llm import FakeProvider
from tests.db.data import RETRIEVAL_HTML
from tests.ingest.fixtures import source

DEAD_ENDS = "Dead ends must be limited in length to thirty metres."


async def _corpus(engine: AsyncEngine) -> None:
    embedder = BagOfWordsEmbedder()
    async with AsyncSession(engine) as session, session.begin():
        stored = await ingest(session, source(RETRIEVAL_HTML))
    async with AsyncSession(engine) as session, session.begin():
        await embed_version(session, stored.version_id, embedder)


async def test_a_question_gets_a_verified_answer(owner_engine: AsyncEngine) -> None:
    await _corpus(owner_engine)
    provider = FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]')

    async with AsyncSession(owner_engine) as session:
        result = await answer_question(
            session,
            "How long can a dead end be?",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )

    assert result.answered
    assert result.sources[0].heading_path.endswith("Escape routes")
    assert result.verification is not None
    assert result.verification.may_show


async def test_a_question_with_a_fabricated_quote_is_refused(owner_engine: AsyncEngine) -> None:
    await _corpus(owner_engine)
    provider = FakeProvider(
        text='The limit is ten metres: "Dead ends must be limited to ten metres." [1]'
    )

    async with AsyncSession(owner_engine) as session:
        result = await answer_question(
            session,
            "How long can a dead end be?",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )

    assert not result.answered
    assert result.refusal is RefusalReason.UNVERIFIED


async def test_a_question_the_corpus_cannot_answer_is_refused(owner_engine: AsyncEngine) -> None:
    """Nothing retrieved means the model is not called at all."""
    await _corpus(owner_engine)
    provider = FakeProvider(text="anything")

    async with AsyncSession(owner_engine) as session:
        result = await answer_question(
            session,
            "zzzz",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )

    assert result.refusal in {RefusalReason.NO_SOURCES, RefusalReason.UNVERIFIED}
    if result.refusal is RefusalReason.NO_SOURCES:
        assert provider.calls == []
