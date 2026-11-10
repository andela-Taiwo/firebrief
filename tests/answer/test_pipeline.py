from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from firebrief.answer.judge import FixedJudge
from firebrief.answer.pipeline import (
    BudgetScope,
    RefusalReason,
    answer_from_sources,
)
from firebrief.answer.prompt import INSUFFICIENT_EVIDENCE, build_prompt
from firebrief.budget import (
    BudgetService,
    InMemoryLedger,
    Limit,
    LimitBook,
    ModelPrice,
    Period,
    PriceTable,
    ScopeType,
)
from firebrief.llm import FakeProvider, ProviderServerError
from firebrief.retrieval.types import Retrieved

DEAD_ENDS = "Dead ends must be limited in length to thirty metres."
ANSWER = f'Dead ends are capped: "{DEAD_ENDS}" [1]'
SCOPE = BudgetScope(org_id="o1", team_id="t1", user_id="u1")


def source(text: str = DEAD_ENDS) -> Retrieved:
    return Retrieved(
        chunk_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        heading_path="Doc > Escape routes",
        text=text,
        score=0.5,
        vector_rank=1,
        text_rank=1,
        embedding_model="bow-1024",
        document_title="Fire safety in flats",
        edition="2019",
        source_url="https://www.gov.uk/doc",
    )


def budget_service(limit: int) -> tuple[BudgetService, InMemoryLedger]:
    ledger = InMemoryLedger()
    service = BudgetService(
        ledger=ledger,
        limits=LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, limit)]),
        prices=PriceTable("GBP", {"model-x": ModelPrice(3_000_000, 15_000_000)}),
        clock=lambda: datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
    )
    return service, ledger


async def test_a_verified_answer_is_returned_with_its_sources() -> None:
    provider = FakeProvider(text=ANSWER)

    result = await answer_from_sources(
        "How long can a dead end be?", [source()], provider=provider, judge=FixedJudge()
    )

    assert result.answered
    assert result.answer == ANSWER
    assert result.verification is not None
    assert result.verification.may_show
    assert len(result.sources) == 1


async def test_a_fabricated_quote_is_refused_as_unverified() -> None:
    provider = FakeProvider(
        text='Dead ends are capped at ten metres: "Dead ends must be limited to ten metres." [1]'
    )

    result = await answer_from_sources(
        "How long can a dead end be?", [source()], provider=provider, judge=FixedJudge()
    )

    assert not result.answered
    assert result.refusal is RefusalReason.UNVERIFIED
    assert result.verification is not None
    assert not result.verification.may_show


async def test_the_model_can_decline() -> None:
    provider = FakeProvider(text=INSUFFICIENT_EVIDENCE)

    result = await answer_from_sources(
        "What colour is the front door?", [source()], provider=provider, judge=FixedJudge()
    )

    assert result.refusal is RefusalReason.INSUFFICIENT_EVIDENCE


async def test_no_sources_means_no_model_call() -> None:
    provider = FakeProvider(text=ANSWER)

    result = await answer_from_sources(
        "How long can a dead end be?", [], provider=provider, judge=FixedJudge()
    )

    assert result.refusal is RefusalReason.NO_SOURCES
    assert provider.calls == []


async def test_a_provider_failure_is_a_refusal_not_an_exception() -> None:
    provider = FakeProvider(text=ANSWER, failures=(ProviderServerError("down"),) * 3)

    result = await answer_from_sources(
        "How long can a dead end be?", [source()], provider=provider, judge=FixedJudge()
    )

    assert result.refusal is RefusalReason.MODEL_UNAVAILABLE


async def test_a_budget_rejection_stops_the_call() -> None:
    provider = FakeProvider(text=ANSWER)
    service, _ = budget_service(limit=1)

    result = await answer_from_sources(
        "How long can a dead end be?",
        [source()],
        provider=provider,
        judge=FixedJudge(),
        model="model-x",
        budget=service,
        scope=SCOPE,
    )

    assert result.refusal is RefusalReason.BUDGET_EXHAUSTED
    assert provider.calls == []


async def test_a_successful_answer_settles_its_reservation() -> None:
    provider = FakeProvider(text=ANSWER)
    service, ledger = budget_service(limit=10_000_000)

    result = await answer_from_sources(
        "How long can a dead end be?",
        [source()],
        provider=provider,
        judge=FixedJudge(),
        model="model-x",
        budget=service,
        scope=SCOPE,
    )

    assert result.answered
    counters = ledger.snapshot()
    assert sum(counter.spent for counter in counters.values()) > 0
    assert all(counter.reserved == 0 for counter in counters.values())


async def test_a_failed_call_releases_its_reservation() -> None:
    provider = FakeProvider(text=ANSWER, failures=(ProviderServerError("down"),) * 3)
    service, ledger = budget_service(limit=10_000_000)

    result = await answer_from_sources(
        "How long can a dead end be?",
        [source()],
        provider=provider,
        judge=FixedJudge(),
        model="model-x",
        budget=service,
        scope=SCOPE,
    )

    assert result.refusal is RefusalReason.MODEL_UNAVAILABLE
    assert all(counter.reserved == 0 for counter in ledger.snapshot().values())


async def test_the_prompt_numbers_the_sources_and_states_the_contract() -> None:
    provider = FakeProvider(text=ANSWER)
    await answer_from_sources(
        "How long can a dead end be?", [source()], provider=provider, judge=FixedJudge()
    )

    system = provider.calls[0].messages[0].content
    user = provider.calls[0].messages[1].content

    assert "verbatim quote" in system
    assert INSUFFICIENT_EVIDENCE in system
    assert "[1]" in user
    assert "How long can a dead end be?" in user
    assert DEAD_ENDS in user


def test_a_prompt_needs_a_source() -> None:
    with pytest.raises(ValueError):
        build_prompt("question", [])


async def test_a_budget_without_a_scope_is_refused() -> None:
    service, _ = budget_service(limit=10_000_000)

    with pytest.raises(ValueError, match="scope"):
        await answer_from_sources(
            "question", [source()], provider=FakeProvider(), judge=FixedJudge(), budget=service
        )
