from __future__ import annotations

import threading
from datetime import UTC, date, datetime, timedelta

import pytest

from firebrief.budget.ledger import CounterKey, InMemoryLedger
from firebrief.budget.limits import Limit, LimitBook, Period, ScopeType
from firebrief.budget.pricing import PriceTable
from firebrief.budget.service import (
    BudgetConfigurationError,
    BudgetPolicy,
    BudgetService,
    ReservationNotPendingError,
    UnknownReservationError,
)

SCOPES = {"org_id": "o1", "team_id": "t1", "user_id": "u1"}


def reserve(service: BudgetService, *, cost_tokens: int = 100, request_id: str = "r1"):
    """A request whose worst case costs 300 micros (100 in x1 + 100 out x2)."""
    return service.reserve(
        request_id=request_id,
        model="tiny",
        prompt_tokens=cost_tokens,
        max_output_tokens=cost_tokens,
        **SCOPES,
    )


def user_daily(day: date = date(2026, 11, 9)) -> CounterKey:
    return CounterKey(ScopeType.USER, "u1", Period.DAILY, day)


def test_reserve_then_settle_at_exact_usage(service: BudgetService, ledger: InMemoryLedger) -> None:
    decision = reserve(service)
    assert decision.admitted
    assert decision.reservation is not None
    assert decision.reservation.amount == 300
    assert ledger.snapshot()[user_daily()].reserved == 300

    settlement = service.settle(decision.reservation.id, input_tokens=10, output_tokens=5)

    assert settlement.charged == 20
    assert settlement.overage == 0
    counter = ledger.snapshot()[user_daily()]
    assert counter.reserved == 0
    assert counter.spent == 20


def test_release_returns_the_reservation(service: BudgetService, ledger: InMemoryLedger) -> None:
    decision = reserve(service)
    assert decision.reservation is not None

    service.release(decision.reservation.id)

    counter = ledger.snapshot()[user_daily()]
    assert counter.reserved == 0
    assert counter.spent == 0


def test_reservations_are_all_or_nothing(prices: PriceTable, clock, ledger: InMemoryLedger) -> None:
    limits = LimitBook(
        [
            Limit(ScopeType.ORG, "o1", Period.DAILY, 500),
            Limit(ScopeType.USER, "u1", Period.DAILY, 10_000),
        ]
    )
    service = BudgetService(ledger=ledger, limits=limits, prices=prices, clock=clock)

    assert reserve(service, request_id="r1").admitted
    second = reserve(service, request_id="r2")

    assert not second.admitted
    snapshot = ledger.snapshot()
    org_key = CounterKey(ScopeType.ORG, "o1", Period.DAILY, date(2026, 11, 9))
    assert snapshot[org_key].reserved == 300
    # The user level must not have been charged for a request the org refused.
    assert snapshot[user_daily()].reserved == 300


def test_hard_limit_rejection_names_the_reset_time(
    prices: PriceTable, clock, ledger: InMemoryLedger
) -> None:
    limits = LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, 1_000)])
    service = BudgetService(
        ledger=ledger,
        limits=limits,
        prices=prices,
        clock=clock,
        policy=BudgetPolicy(fallback_model="tiny-cheap"),
    )

    for index in range(3):
        assert reserve(service, request_id=f"r{index}").admitted
    decision = reserve(service, request_id="r4")

    assert not decision.admitted
    assert decision.rejection is not None
    assert decision.rejection.used == 900
    assert decision.rejection.reset_at == datetime(2026, 11, 10, tzinfo=UTC)
    assert decision.fallback_model == "tiny-cheap"


def test_soft_limit_warns_before_it_blocks(
    prices: PriceTable, clock, ledger: InMemoryLedger
) -> None:
    limits = LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, 1_000)])
    service = BudgetService(
        ledger=ledger, limits=limits, prices=prices, clock=clock, policy=BudgetPolicy()
    )

    assert reserve(service, request_id="r1").warnings == ()
    assert reserve(service, request_id="r2").warnings == ()
    warned = reserve(service, request_id="r3")

    assert warned.admitted
    assert len(warned.warnings) == 1
    assert warned.warnings[0].ratio == pytest.approx(0.9)


def test_daily_limit_resets_at_utc_midnight(
    prices: PriceTable, clock, ledger: InMemoryLedger
) -> None:
    limits = LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, 1_000)])
    service = BudgetService(ledger=ledger, limits=limits, prices=prices, clock=clock)

    for index in range(3):
        reserve(service, request_id=f"r{index}")
    clock.now = datetime(2026, 11, 10, 0, 1, tzinfo=UTC)

    assert reserve(service, request_id="tomorrow").admitted


def test_organisation_limit_is_shared_across_users(
    prices: PriceTable, clock, ledger: InMemoryLedger
) -> None:
    limits = LimitBook(
        [
            Limit(ScopeType.ORG, "o1", Period.MONTHLY, 1_000),
            Limit(ScopeType.USER, "u1", Period.MONTHLY, 10_000),
            Limit(ScopeType.USER, "u2", Period.MONTHLY, 10_000),
        ]
    )
    service = BudgetService(ledger=ledger, limits=limits, prices=prices, clock=clock)

    for index in range(3):
        assert service.reserve(
            request_id=f"a{index}",
            org_id="o1",
            team_id="t1",
            user_id="u1",
            model="tiny",
            prompt_tokens=100,
            max_output_tokens=100,
        ).admitted
    blocked = service.reserve(
        request_id="b0",
        org_id="o1",
        team_id="t1",
        user_id="u2",
        model="tiny",
        prompt_tokens=100,
        max_output_tokens=100,
    )

    assert not blocked.admitted
    assert blocked.rejection is not None
    assert blocked.rejection.limit.scope_type is ScopeType.ORG


def test_settlement_clamps_to_the_reservation_and_records_the_overage(
    service: BudgetService, ledger: InMemoryLedger
) -> None:
    decision = reserve(service)  # reserves 300
    assert decision.reservation is not None

    settlement = service.settle(decision.reservation.id, input_tokens=100, output_tokens=500)

    assert settlement.reserved == 300
    assert settlement.charged == 300
    assert settlement.overage == 800
    counter = ledger.snapshot()[user_daily()]
    assert counter.spent == 300
    assert counter.used <= 10_000


def test_sweep_releases_abandoned_reservations(
    service: BudgetService, clock, ledger: InMemoryLedger
) -> None:
    decision = reserve(service)
    assert decision.reservation is not None

    clock.now = clock.now + timedelta(minutes=11)
    released = service.sweep()

    assert released == 1
    assert ledger.snapshot()[user_daily()].reserved == 0


def test_unknown_and_settled_reservations_are_rejected(service: BudgetService) -> None:
    with pytest.raises(UnknownReservationError):
        service.settle("nope", input_tokens=1, output_tokens=1)

    decision = reserve(service)
    assert decision.reservation is not None
    service.settle(decision.reservation.id, input_tokens=1, output_tokens=1)
    with pytest.raises(ReservationNotPendingError):
        service.release(decision.reservation.id)


def test_no_configured_limit_fails_loudly(
    prices: PriceTable, clock, ledger: InMemoryLedger
) -> None:
    service = BudgetService(ledger=ledger, limits=LimitBook([]), prices=prices, clock=clock)
    with pytest.raises(BudgetConfigurationError):
        reserve(service)


def test_concurrent_requests_cannot_overspend(
    prices: PriceTable, clock, ledger: InMemoryLedger
) -> None:
    limits = LimitBook([Limit(ScopeType.USER, "u1", Period.DAILY, 5_000)])
    service = BudgetService(ledger=ledger, limits=limits, prices=prices, clock=clock)
    barrier = threading.Barrier(8)
    decisions = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        decision = service.reserve(
            request_id="concurrent",
            org_id="o1",
            team_id="t1",
            user_id="u1",
            model="tiny",
            prompt_tokens=0,
            max_output_tokens=500,  # costs exactly 1000 micros
        )
        with lock:
            decisions.append(decision)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    admitted = [decision for decision in decisions if decision.admitted]
    assert len(admitted) == 5
    assert ledger.snapshot()[user_daily()].used == 5_000
