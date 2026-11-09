from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from firebrief.budget.ledger import InMemoryLedger
from firebrief.budget.limits import Limit, LimitBook, Period, ScopeType
from firebrief.budget.pricing import ModelPrice, PriceTable
from firebrief.budget.service import BudgetPolicy, BudgetService


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now = self.now + timedelta(**kwargs)


@pytest.fixture
def prices() -> PriceTable:
    # 1.00 input / 2.00 output per million tokens => 1 and 2 micros per token.
    return PriceTable(currency="GBP", models={"tiny": ModelPrice(1_000_000, 2_000_000)})


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 11, 9, 12, 0, tzinfo=UTC))


@pytest.fixture
def limits() -> LimitBook:
    return LimitBook(
        [
            Limit(ScopeType.USER, "u1", Period.DAILY, 10_000),
            Limit(ScopeType.USER, "u1", Period.MONTHLY, 100_000),
        ]
    )


@pytest.fixture
def ledger() -> InMemoryLedger:
    return InMemoryLedger()


@pytest.fixture
def service(
    prices: PriceTable, clock: MutableClock, limits: LimitBook, ledger: InMemoryLedger
) -> BudgetService:
    return BudgetService(
        ledger=ledger,
        limits=limits,
        prices=prices,
        clock=clock,
        policy=BudgetPolicy(fallback_model="tiny-cheap"),
    )
