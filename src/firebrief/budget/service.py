"""Estimate -> reserve -> settle / release.

Every request reserves its worst-case cost at every level of the hierarchy
before the model is called. The reservation is settled at the provider's exact
usage, or released if the call fails. A concurrent request therefore cannot
overspend a limit: it is refused before it can start.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from firebrief.budget.ledger import CounterKey, Ledger
from firebrief.budget.limits import Limit, LimitBook, Period, ScopeType
from firebrief.budget.money import Money
from firebrief.budget.pricing import PriceTable

Clock = Callable[[], datetime]


class BudgetError(Exception):
    """Base class for budget failures."""


class BudgetConfigurationError(BudgetError):
    """Raised when no limit applies to a request, or a limit cannot be applied."""


class UnknownReservationError(BudgetError):
    """Raised when a reservation id is not known to the store."""


class ReservationNotPendingError(BudgetError):
    """Raised when a reservation is settled or released twice."""


class ReservationState(StrEnum):
    PENDING = "pending"
    SETTLED = "settled"
    RELEASED = "released"


@dataclass(slots=True)
class Reservation:
    id: str
    request_id: str
    model: str
    amount: Money
    keys: tuple[CounterKey, ...]
    created_at: datetime
    expires_at: datetime
    state: ReservationState = ReservationState.PENDING


@dataclass(frozen=True, slots=True)
class BudgetWarning:
    limit: Limit
    used: Money
    amount: Money
    ratio: float


@dataclass(frozen=True, slots=True)
class Rejection:
    limit: Limit
    used: Money
    amount: Money
    reset_at: datetime


@dataclass(frozen=True, slots=True)
class Decision:
    admitted: bool
    reservation: Reservation | None = None
    warnings: tuple[BudgetWarning, ...] = ()
    rejection: Rejection | None = None
    fallback_model: str | None = None
    """Set when the policy allows a cheaper model to be tried instead."""


@dataclass(frozen=True, slots=True)
class Settlement:
    reservation_id: str
    reserved: Money
    charged: Money
    overage: Money
    warnings: tuple[BudgetWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    soft_ratio: float = 0.8
    fallback_model: str | None = None
    reservation_ttl: timedelta = timedelta(minutes=10)

    def __post_init__(self) -> None:
        if not 0 < self.soft_ratio < 1:
            raise ValueError("soft_ratio must be between 0 and 1")
        if self.reservation_ttl <= timedelta(0):
            raise ValueError("reservation_ttl must be positive")


class ReservationStore(Protocol):
    def add(self, reservation: Reservation) -> None: ...

    def get(self, reservation_id: str) -> Reservation | None: ...

    def pending(self) -> tuple[Reservation, ...]: ...


class InMemoryReservationStore:
    def __init__(self) -> None:
        self._items: dict[str, Reservation] = {}
        self._lock = threading.RLock()

    def add(self, reservation: Reservation) -> None:
        with self._lock:
            self._items[reservation.id] = reservation

    def get(self, reservation_id: str) -> Reservation | None:
        with self._lock:
            return self._items.get(reservation_id)

    def pending(self) -> tuple[Reservation, ...]:
        with self._lock:
            return tuple(r for r in self._items.values() if r.state is ReservationState.PENDING)


def utcnow() -> datetime:
    return datetime.now(UTC)


def period_start(now: datetime, period: Period) -> date:
    today = now.astimezone(UTC).date()
    if period is Period.DAILY:
        return today
    return today.replace(day=1)


def utc_day(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def period_reset_at(now: datetime, period: Period) -> datetime:
    """Midnight UTC at the end of the period that contains `now`."""
    if period is Period.DAILY:
        return utc_day(now.astimezone(UTC).date()) + timedelta(days=1)
    current = now.astimezone(UTC).date()
    if current.month == 12:
        return datetime(current.year + 1, 1, 1, tzinfo=UTC)
    return datetime(current.year, current.month + 1, 1, tzinfo=UTC)


def _ratio(used: Money, amount: Money, limit: Money) -> float:
    return (used + amount) / limit


@dataclass
class BudgetService:
    ledger: Ledger
    limits: LimitBook
    prices: PriceTable
    store: ReservationStore = field(default_factory=InMemoryReservationStore)
    policy: BudgetPolicy = field(default_factory=BudgetPolicy)
    clock: Clock = utcnow

    def estimate(self, *, model: str, prompt_tokens: int, max_output_tokens: int) -> Money:
        """The worst-case cost of one request, in micros."""
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if prompt_tokens < 0:
            raise ValueError("prompt_tokens must not be negative")
        return self.prices.price(model).worst_case(prompt_tokens, max_output_tokens)

    def reserve(
        self,
        *,
        request_id: str,
        org_id: str,
        team_id: str,
        user_id: str,
        model: str,
        prompt_tokens: int,
        max_output_tokens: int,
    ) -> Decision:
        amount = self.estimate(
            model=model, prompt_tokens=prompt_tokens, max_output_tokens=max_output_tokens
        )
        limits = self.limits.for_ids(org_id=org_id, team_id=team_id, user_id=user_id)
        if not limits:
            raise BudgetConfigurationError(
                f"no limit is configured for org={org_id!r} team={team_id!r} user={user_id!r}"
            )
        now = self.clock()
        entries = [
            (
                limit,
                CounterKey(
                    limit.scope_type, limit.scope_id, limit.period, period_start(now, limit.period)
                ),
            )
            for limit in limits
        ]

        with self.ledger.transaction() as txn:
            warnings: list[BudgetWarning] = []
            failures: list[Rejection] = []
            for limit, key in entries:
                counter = txn.get(key)
                ratio = _ratio(counter.used, amount, limit.amount)
                if counter.used + amount > limit.amount:
                    failures.append(
                        Rejection(limit, counter.used, amount, period_reset_at(now, limit.period))
                    )
                elif ratio >= self.policy.soft_ratio:
                    warnings.append(BudgetWarning(limit, counter.used, amount, ratio))

            if failures:
                worst = max(failures, key=lambda r: _ratio(r.used, r.amount, r.limit.amount))
                return Decision(
                    admitted=False,
                    rejection=worst,
                    fallback_model=self.policy.fallback_model,
                )

            for _limit, key in entries:
                counter = txn.get(key)
                txn.set(key, replace(counter, reserved=counter.reserved + amount))

            reservation = Reservation(
                id=str(uuid.uuid4()),
                request_id=request_id,
                model=model,
                amount=amount,
                keys=tuple(key for _, key in entries),
                created_at=now,
                expires_at=now + self.policy.reservation_ttl,
            )
            self.store.add(reservation)

        return Decision(admitted=True, reservation=reservation, warnings=tuple(warnings))

    def settle(self, reservation_id: str, *, input_tokens: int, output_tokens: int) -> Settlement:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must not be negative")
        reservation = self._require_pending(reservation_id)
        charged = self.prices.price(reservation.model).cost(input_tokens, output_tokens)
        effective = min(charged, reservation.amount)
        overage = charged - effective
        now = self.clock()

        with self.ledger.transaction() as txn:
            for key in reservation.keys:
                counter = txn.get(key)
                txn.set(
                    key,
                    replace(
                        counter,
                        reserved=counter.reserved - reservation.amount,
                        spent=counter.spent + effective,
                    ),
                )
            self.store.add(replace(reservation, state=ReservationState.SETTLED))

        return Settlement(
            reservation_id=reservation_id,
            reserved=reservation.amount,
            charged=effective,
            overage=overage,
            warnings=self._warnings_now(reservation, now),
        )

    def release(self, reservation_id: str) -> None:
        reservation = self._require_pending(reservation_id)
        with self.ledger.transaction() as txn:
            for key in reservation.keys:
                counter = txn.get(key)
                txn.set(key, replace(counter, reserved=counter.reserved - reservation.amount))
            self.store.add(replace(reservation, state=ReservationState.RELEASED))

    def sweep(self, now: datetime | None = None) -> int:
        """Release reservations whose holder died before settling them."""
        moment = now or self.clock()
        released = 0
        for reservation in self.store.pending():
            if reservation.expires_at <= moment:
                self.release(reservation.id)
                released += 1
        return released

    def _require_pending(self, reservation_id: str) -> Reservation:
        reservation = self.store.get(reservation_id)
        if reservation is None:
            raise UnknownReservationError(reservation_id)
        if reservation.state is not ReservationState.PENDING:
            raise ReservationNotPendingError(
                f"reservation {reservation_id} is {reservation.state.value}"
            )
        return reservation

    def _warnings_now(self, reservation: Reservation, now: datetime) -> tuple[BudgetWarning, ...]:
        warnings: list[BudgetWarning] = []
        limits = self.limits.for_ids(
            org_id=_scope_id(reservation, ScopeType.ORG),
            team_id=_scope_id(reservation, ScopeType.TEAM),
            user_id=_scope_id(reservation, ScopeType.USER),
        )
        with self.ledger.transaction() as txn:
            for limit in limits:
                key = CounterKey(
                    limit.scope_type, limit.scope_id, limit.period, period_start(now, limit.period)
                )
                counter = txn.get(key)
                ratio = counter.used / limit.amount
                if ratio >= self.policy.soft_ratio:
                    warnings.append(BudgetWarning(limit, counter.used, 0, ratio))
        return tuple(warnings)


def _scope_id(reservation: Reservation, scope_type: ScopeType) -> str:
    for key in reservation.keys:
        if key.scope_type is scope_type:
            return key.scope_id
    return ""
