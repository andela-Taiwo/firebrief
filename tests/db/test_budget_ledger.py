from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.budget import (
    BudgetPolicy,
    BudgetService,
    Limit,
    LimitBook,
    ModelPrice,
    Period,
    PriceTable,
    ReservationNotPendingError,
    ScopeType,
)
from firebrief.budget.ledger import CounterKey
from firebrief.budget.postgres import PostgresLedger

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
PRICES = PriceTable("GBP", {"tiny": ModelPrice(1_000_000, 2_000_000)})
SCOPES = {"org_id": "o1", "team_id": "t1", "user_id": "u1"}


def make_service(engine: AsyncEngine, *, limit: int = 10_000) -> BudgetService:
    return BudgetService(
        ledger=PostgresLedger(engine),
        limits=LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, limit)]),
        prices=PRICES,
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
    async with PostgresLedger(app_engine).transaction() as txn:
        snapshot = await txn.get_reservation(decision.reservation.id)
    assert snapshot is not None
    assert snapshot.state == "settled"


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


async def test_a_failed_add_leaves_the_counters_untouched(
    app_engine: AsyncEngine,
    seeded,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Capacity and reservation commit together, or not at all."""
    from firebrief.budget import postgres

    async def explode(self, reservation):  # type: ignore[no-untyped-def]
        raise RuntimeError("reservation write failed")

    monkeypatch.setattr(postgres._PostgresTransaction, "add", explode)
    service = make_service(app_engine)

    with pytest.raises(RuntimeError):
        await _reserve(service)

    async with PostgresLedger(app_engine).transaction() as txn:
        counter = await txn.get(_user_key())
    assert counter.reserved == 0
    assert counter.spent == 0


async def test_settle_and_sweep_cannot_both_finish_one_reservation(
    app_engine: AsyncEngine, seeded
) -> None:
    import asyncio

    first = make_service(app_engine)
    decision = await _reserve(first)
    assert decision.reservation is not None

    later = NOW + timedelta(minutes=11)
    second = BudgetService(
        ledger=PostgresLedger(app_engine),
        limits=LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, 10_000)]),
        prices=PRICES,
        clock=lambda: later,
    )

    outcomes = await asyncio.gather(
        second.settle(decision.reservation.id, input_tokens=10, output_tokens=5),
        second.sweep(),
        return_exceptions=True,
    )

    finished = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    assert finished, "one of the two must have finished the reservation"

    # Whichever won, the reservation is finished: another finisher must be refused.
    with pytest.raises(ReservationNotPendingError):
        await second.settle(decision.reservation.id, input_tokens=1, output_tokens=1)

    async with PostgresLedger(app_engine).transaction() as txn:
        counter = await txn.get(_user_key())
        stored = await txn.get_reservation(decision.reservation.id)
    assert counter.reserved == 0, "capacity is returned exactly once"
    assert stored is not None
    assert stored.state in {"settled", "released"}


async def test_two_users_sharing_an_organisation_do_not_deadlock(
    app_engine: AsyncEngine, seeded
) -> None:
    import asyncio

    service = BudgetService(
        ledger=PostgresLedger(app_engine),
        limits=LimitBook(
            [
                Limit(ScopeType.ORG, "o1", Period.DAILY, 1_000_000),
                Limit(ScopeType.USER, "u1", Period.DAILY, 1_000_000),
                Limit(ScopeType.USER, "u2", Period.DAILY, 1_000_000),
            ]
        ),
        prices=PRICES,
        clock=lambda: NOW,
    )

    async def attempt(user: str, request_id: str) -> bool:
        decision = await service.reserve(
            request_id=request_id,
            org_id="o1",
            team_id="t1",
            user_id=user,
            model="tiny",
            prompt_tokens=10,
            max_output_tokens=10,
        )
        return decision.admitted

    # Overlapping keys (the org) taken in a fixed order: neither transaction deadlocks.
    results = await asyncio.gather(attempt("u1", "d1"), attempt("u2", "d2"))

    assert all(results)


async def test_the_same_request_id_reserves_once(app_engine: AsyncEngine, seeded) -> None:
    service = make_service(app_engine)

    first = await _reserve(service, request_id="retry-me")
    second = await _reserve(service, request_id="retry-me")

    assert first.reservation is not None
    assert second.reservation is not None
    assert first.reservation.id == second.reservation.id
    async with PostgresLedger(app_engine).transaction() as txn:
        counter = await txn.get(_user_key())
    assert counter.reserved == first.reservation.amount


def _user_key() -> CounterKey:
    return CounterKey(ScopeType.USER, "u1", Period.DAILY, NOW.date())
