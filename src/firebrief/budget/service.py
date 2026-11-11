"""Estimate -> reserve -> settle / release.

Every request reserves its worst-case cost at every level of the hierarchy
before the model is called. The reservation is settled at the provider's exact
usage, or released if the call fails. A concurrent request therefore cannot
overspend a limit: it is refused before it can start.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from firebrief.budget.ledger import CounterKey, Ledger, Reservation
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
    policy: BudgetPolicy = field(default_factory=BudgetPolicy)
    clock: Clock = utcnow

    def estimate(self, *, model: str, prompt_tokens: int, max_output_tokens: int) -> Money:
        """The worst-case cost of one request, in micros."""
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if prompt_tokens < 0:
            raise ValueError("prompt_tokens must not be negative")
        return self.prices.price(model).worst_case(prompt_tokens, max_output_tokens)

    async def reserve(
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
        # A fixed order across every transaction, so two overlapping reservations cannot
        # take the same rows in opposite orders and deadlock.
        entries.sort(key=lambda item: item[1].sort_key())

        reservation = Reservation(
            id=str(uuid.uuid4()),
            request_id=request_id,
            model=model,
            amount=amount,
            keys=tuple(key for _, key in entries),
            created_at=now,
            expires_at=now + self.policy.reservation_ttl,
        )

        async with self.ledger.transaction() as txn:
            warnings: list[BudgetWarning] = []
            failures: list[Rejection] = []
            for limit, key in entries:
                counter = await txn.get(key)
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

            # Idempotent by request id: a retried request returns the reservation it
            # already has instead of reserving twice.
            stored = await txn.add(reservation)
            if stored.id != reservation.id:
                return Decision(admitted=True, reservation=stored, warnings=())

            for _limit, key in entries:
                counter = await txn.get(key)
                await txn.set(key, replace(counter, reserved=counter.reserved + amount))

        return Decision(admitted=True, reservation=reservation, warnings=tuple(warnings))

    async def settle(
        self, reservation_id: str, *, input_tokens: int, output_tokens: int
    ) -> Settlement:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must not be negative")
        now = self.clock()

        async with self.ledger.transaction() as txn:
            reservation = await txn.claim(reservation_id, ReservationState.SETTLED.value)
            if reservation is None:
                await _raise_not_pending(txn, reservation_id)
                raise AssertionError("unreachable")

            charged = self.prices.price(reservation.model).cost(input_tokens, output_tokens)
            effective = min(charged, reservation.amount)
            for key in reservation.keys:
                counter = await txn.get(key)
                await txn.set(
                    key,
                    replace(
                        counter,
                        reserved=counter.reserved - reservation.amount,
                        spent=counter.spent + effective,
                    ),
                )

        return Settlement(
            reservation_id=reservation_id,
            reserved=reservation.amount,
            charged=effective,
            overage=charged - effective,
            warnings=await self._warnings_now(reservation, now),
        )

    async def release(self, reservation_id: str) -> None:
        async with self.ledger.transaction() as txn:
            reservation = await txn.claim(reservation_id, ReservationState.RELEASED.value)
            if reservation is None:
                await _raise_not_pending(txn, reservation_id)
                raise AssertionError("unreachable")
            for key in reservation.keys:
                counter = await txn.get(key)
                await txn.set(key, replace(counter, reserved=counter.reserved - reservation.amount))

    async def sweep(self, now: datetime | None = None, limit: int = 100) -> int:
        """Release reservations whose holder died before settling them.

        The claim makes it safe to run on several instances: each expired row is only
        released once, and rows another instance is working on are skipped.
        """
        moment = now or self.clock()
        released = 0
        async with self.ledger.transaction() as txn:
            for reservation in await txn.expired(moment, limit):
                claimed = await txn.claim(reservation.id, ReservationState.RELEASED.value)
                if claimed is None:
                    continue
                for key in claimed.keys:
                    counter = await txn.get(key)
                    await txn.set(key, replace(counter, reserved=counter.reserved - claimed.amount))
                released += 1
        return released

    async def _warnings_now(
        self, reservation: Reservation, now: datetime
    ) -> tuple[BudgetWarning, ...]:
        warnings: list[BudgetWarning] = []
        limits = self.limits.for_ids(
            org_id=_scope_id(reservation, ScopeType.ORG),
            team_id=_scope_id(reservation, ScopeType.TEAM),
            user_id=_scope_id(reservation, ScopeType.USER),
        )
        async with self.ledger.transaction() as txn:
            for limit in limits:
                key = CounterKey(
                    limit.scope_type, limit.scope_id, limit.period, period_start(now, limit.period)
                )
                counter = await txn.get(key)
                ratio = counter.used / limit.amount
                if ratio >= self.policy.soft_ratio:
                    warnings.append(BudgetWarning(limit, counter.used, 0, ratio))
        return tuple(warnings)


async def _raise_not_pending(txn, reservation_id: str) -> None:  # type: ignore[no-untyped-def]
    existing = await txn.get_reservation(reservation_id)
    if existing is None:
        raise UnknownReservationError(reservation_id)
    raise ReservationNotPendingError(f"reservation {reservation_id} is {existing.state}")


def _scope_id(reservation: Reservation, scope_type: ScopeType) -> str:
    for key in reservation.keys:
        if key.scope_type is scope_type:
            return key.scope_id
    return ""
