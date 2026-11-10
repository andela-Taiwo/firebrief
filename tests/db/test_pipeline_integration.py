from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from firebrief.answer import FixedJudge, RefusalReason, answer_question
from firebrief.ingest.embed import BagOfWordsEmbedder, Embedder
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


async def test_without_a_relevance_floor_an_unrelated_question_reaches_the_model(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """Documents current behaviour: no floor means the top k always reach the model."""
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


async def test_a_relevance_floor_returns_no_sources_without_calling_the_model(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    await _corpus(owner_engine)
    provider = FakeProvider(text="anything at all")

    async with AsyncSession(app_engine) as session:
        result = await answer_question(
            session,
            "zzzz qqqq",
            embedder=BagOfWordsEmbedder(),
            provider=provider,
            judge=FixedJudge(),
            min_similarity=0.05,
        )

    assert result.refusal_reason is RefusalReason.NO_SOURCES
    assert provider.calls == []


class RecordingEmbedder:
    """Records every string it is asked to embed, so a leak is visible."""

    def __init__(self, inner: Embedder) -> None:
        self.inner = inner
        self.texts: list[str] = []

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def dimensions(self) -> int:
        return self.inner.dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return await self.inner.embed(texts)


async def test_personal_data_never_reaches_the_embedding_provider(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """The query embedding is a third-party call: it must see redacted text."""
    await _corpus(owner_engine)
    embedder = RecordingEmbedder(BagOfWordsEmbedder())
    provider = FakeProvider(text=f'The limit is thirty metres: "{DEAD_ENDS}" [1]')
    question = "I am ada@example.com, how long can a dead end be?"

    async with AsyncSession(app_engine) as session:
        result = await answer_question(
            session,
            question,
            embedder=embedder,
            provider=provider,
            judge=FixedJudge(),
        )

    assert embedder.texts, "the query was embedded"
    assert all("ada@example.com" not in text for text in embedder.texts)
    assert any("[REDACTED:email]" in text for text in embedder.texts)
    assert "ada@example.com" not in result.question
