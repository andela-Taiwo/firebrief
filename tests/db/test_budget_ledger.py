from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.budget import (
    BudgetPolicy,
    BudgetService,
    Limit,
    LimitBook,
    ModelPrice,
    Period,
    PriceTable,
    ScopeType,
)
from firebrief.budget.postgres import PostgresLedger, PostgresReservationStore

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
PRICES = PriceTable("GBP", {"tiny": ModelPrice(1_000_000, 2_000_000)})
SCOPES = {"org_id": "o1", "team_id": "t1", "user_id": "u1"}


def make_service(engine: AsyncEngine, *, limit: int = 10_000) -> BudgetService:
    return BudgetService(
        ledger=PostgresLedger(engine),
        limits=LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, limit)]),
        prices=PRICES,
        store=PostgresReservationStore(engine),
        clock=lambda: NOW,
    )


async def _reserve(service: BudgetService, request_id: str = "r1"):  # type: ignore[no-untyped-def]
    return await service.reserve(
        request_id=request_id,
        model="tiny",
        prompt_tokens=10,
        max_output_tokens=10,
        **SCOPES,
    )


async def test_spend_survives_a_restart(app_engine: AsyncEngine, seeded) -> None:  # type: ignore[no-untyped-def]
    first = make_service(app_engine)
    decision = await _reserve(first)
    assert decision.reservation is not None
    await first.settle(decision.reservation.id, input_tokens=10, output_tokens=5)

    # A brand-new service reads the same counters: nothing was held in process memory.
    second = make_service(app_engine)
    blocked = await second.reserve(
        request_id="r2",
        model="tiny",
        prompt_tokens=0,
        max_output_tokens=10_000,  # 20_000 micros, far beyond the limit
        **SCOPES,
    )

    assert not blocked.admitted


async def test_a_reservation_can_be_settled_after_a_restart(
    app_engine: AsyncEngine, seeded
) -> None:  # type: ignore[no-untyped-def]
    first = make_service(app_engine)
    decision = await _reserve(first)
    assert decision.reservation is not None

    second = make_service(app_engine)
    settlement = await second.settle(decision.reservation.id, input_tokens=10, output_tokens=5)

    assert settlement.charged == 20
    snapshot = await second.store.get(decision.reservation.id)
    assert snapshot is not None
    assert snapshot.state.value == "settled"


async def test_an_abandoned_reservation_is_swept_after_a_restart(
    app_engine: AsyncEngine, seeded
) -> None:  # type: ignore[no-untyped-def]
    first = make_service(app_engine)
    decision = await _reserve(first)
    assert decision.reservation is not None

    later = NOW + timedelta(minutes=11)
    second = BudgetService(
        ledger=PostgresLedger(app_engine),
        limits=LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, 10_000)]),
        prices=PRICES,
        store=PostgresReservationStore(app_engine),
        clock=lambda: later,
        policy=BudgetPolicy(reservation_ttl=timedelta(minutes=10)),
    )

    released = await second.sweep()

    assert released == 1
    third = make_service(app_engine)
    allowed = await _reserve(third, request_id="r2")
    assert allowed.admitted, "the abandoned reservation no longer holds capacity"


async def test_two_concurrent_reservations_cannot_both_take_the_last_slot(
    app_engine: AsyncEngine, seeded
) -> None:  # type: ignore[no-untyped-def]
    import asyncio

    # Room for exactly one 20_000-micros reservation (10_000 output tokens at 2 micros).
    service = make_service(app_engine, limit=20_000)

    async def attempt(request_id: str) -> bool:
        decision = await service.reserve(
            request_id=request_id,
            model="tiny",
            prompt_tokens=0,
            max_output_tokens=10_000,
            **SCOPES,
        )
        return decision.admitted

    results = await asyncio.gather(attempt("a"), attempt("b"))

    assert sum(results) == 1
