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


async def test_a_question_gets_a_verified_answer(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """Answered as the runtime role: production never has the owner's grants."""
    await _corpus(owner_engine)
    provider = FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]')

    async with AsyncSession(app_engine) as session:
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


async def test_a_question_with_a_fabricated_quote_is_refused(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await _corpus(owner_engine)
    provider = FakeProvider(
        text='The limit is ten metres: "Dead ends must be limited to ten metres." [1]'
    )

    async with AsyncSession(app_engine) as session:
        result = await answer_question(
            session,
            "How long can a dead end be?",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )

    assert result.refusal_reason is RefusalReason.UNVERIFIED


async def test_an_unanswerable_question_is_refused(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """No floor on similarity, so the model is asked and its uncited answer is refused."""
    await _corpus(owner_engine)
    provider = FakeProvider(text="anything at all")

    async with AsyncSession(app_engine) as session:
        result = await answer_question(
            session,
            "zzzz qqqq",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )

    assert result.refusal_reason is RefusalReason.UNVERIFIED
    assert provider.calls, "the model was consulted; the refusal came after it"


async def test_two_questions_get_different_request_ids(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await _corpus(owner_engine)
    provider = FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]')

    async with AsyncSession(app_engine) as session:
        first = await answer_question(
            session,
            "How long can a dead end be?",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )
        second = await answer_question(
            session,
            "How long can a dead end be?",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
        )

    assert first.request_id
    assert second.request_id
    assert first.request_id != second.request_id
