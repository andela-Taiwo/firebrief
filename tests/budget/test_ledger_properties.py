from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from firebrief.budget.ledger import CounterKey, InMemoryLedger
from firebrief.budget.limits import Limit, LimitBook, Period, ScopeType
from firebrief.budget.pricing import ModelPrice, PriceTable
from firebrief.budget.service import BudgetPolicy, BudgetService, period_start

DAILY_LIMIT = 10_000
MONTHLY_LIMIT = 100_000


def _build():
    clock_now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)

    def clock() -> datetime:
        return clock_now

    ledger = InMemoryLedger()
    limits = LimitBook(
        [
            Limit(ScopeType.USER, "u1", Period.DAILY, DAILY_LIMIT),
            Limit(ScopeType.USER, "u1", Period.MONTHLY, MONTHLY_LIMIT),
        ]
    )
    prices = PriceTable("GBP", {"tiny": ModelPrice(1_000_000, 2_000_000)})
    service = BudgetService(
        ledger=ledger,
        limits=limits,
        prices=prices,
        clock=clock,
        policy=BudgetPolicy(reservation_ttl=timedelta(minutes=10)),
    )
    return service, ledger, clock_now


def _limit_for(key: CounterKey) -> int:
    return MONTHLY_LIMIT if key.period is Period.MONTHLY else DAILY_LIMIT


async def _assert_invariants(service: BudgetService, ledger: InMemoryLedger) -> None:
    pending: dict[CounterKey, int] = defaultdict(int)
    for reservation in ledger.reservations():
        if reservation.state != "pending":
            continue
        for key in reservation.keys:
            pending[key] += reservation.amount

    for key, counter in ledger.snapshot().items():
        assert counter.reserved >= 0, "reserved went negative"
        assert counter.spent >= 0, "spent went negative"
        assert counter.reserved == pending.get(key, 0), (
            "reserved does not match pending reservations"
        )
        assert counter.used <= _limit_for(key), "spend exceeded the limit"


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    ops=st.lists(
        st.tuples(st.sampled_from(["reserve", "settle", "release", "sweep"]), st.integers(0, 5)),
        max_size=25,
    )
)
async def test_operations_always_balance(ops: list[tuple[str, int]]) -> None:
    service, ledger, clock_now = _build()
    pending: list[str] = []
    issued = 0

    for kind, index in ops:
        if kind == "reserve":
            issued += 1
            decision = await service.reserve(
                request_id=f"r{issued}",
                org_id="o1",
                team_id="t1",
                user_id="u1",
                model="tiny",
                prompt_tokens=100,
                max_output_tokens=100,
            )
            if decision.admitted and decision.reservation is not None:
                pending.append(decision.reservation.id)
        elif kind == "settle" and pending:
            await service.settle(pending.pop(index % len(pending)), input_tokens=7, output_tokens=3)
        elif kind == "release" and pending:
            await service.release(pending.pop(index % len(pending)))
        elif kind == "sweep":
            await service.sweep(now=clock_now + timedelta(minutes=11))
            pending.clear()  # everything outstanding is past its TTL and now released

        await _assert_invariants(service, ledger)

    await _assert_invariants(service, ledger)


def test_period_start_is_utc_calendar_aligned() -> None:
    moment = datetime(2026, 3, 31, 23, 59, tzinfo=UTC)
    assert period_start(moment, Period.DAILY) == datetime(2026, 3, 31).date()
    assert period_start(moment, Period.MONTHLY) == datetime(2026, 3, 1).date()
