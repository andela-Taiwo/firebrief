"""The store behind the budget service.

The ledger holds, per (scope, period, period start), the amount reserved and the amount
spent, and it holds the reservations themselves. They live together because they must
commit together: a reservation row that commits without its counters leaks capacity with
nothing to sweep, and counters that commit without a row leak capacity with nothing to
settle.

Every state change goes through `claim`, which is a single conditional update. Two
finishers — a late settle racing the sweeper, or two sweepers on two instances — cannot
both win, because only one of them sees a row come back.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Iterable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime

from firebrief.budget.limits import Period, ScopeType
from firebrief.budget.money import Money


@dataclass(frozen=True, slots=True)
class CounterKey:
    scope_type: ScopeType
    scope_id: str
    period: Period
    period_start: date

    def sort_key(self) -> tuple[str, str, str, date]:
        """A deterministic order, so two transactions cannot deadlock by taking them
        in opposite orders."""
        return (self.scope_type.value, self.scope_id, self.period.value, self.period_start)


@dataclass(frozen=True, slots=True)
class Counter:
    reserved: Money = 0
    spent: Money = 0

    @property
    def used(self) -> Money:
        return self.reserved + self.spent


@dataclass(frozen=True, slots=True)
class Reservation:
    id: str
    request_id: str
    model: str
    amount: Money
    keys: tuple[CounterKey, ...]
    created_at: datetime
    expires_at: datetime
    state: str = "pending"


class LedgerTransaction(ABC):
    """Everything that must happen atomically for one budget change."""

    @abstractmethod
    async def get(self, key: CounterKey) -> Counter: ...

    @abstractmethod
    async def set(self, key: CounterKey, counter: Counter) -> None: ...

    @abstractmethod
    async def peek(self, key: CounterKey) -> Counter:
        """Read without locking or creating a row. For warnings after a settle."""

    @abstractmethod
    async def keys(self) -> Iterable[CounterKey]: ...

    @abstractmethod
    async def add(self, reservation: Reservation) -> Reservation:
        """Insert, or return the reservation already stored for this request id."""

    @abstractmethod
    async def get_reservation(self, reservation_id: str) -> Reservation | None: ...

    @abstractmethod
    async def get_reservation_by_request(self, request_id: str) -> Reservation | None: ...

    @abstractmethod
    async def claim(self, reservation_id: str, state: str) -> Reservation | None:
        """Move a pending reservation to `state`. None means someone else got there first."""

    @abstractmethod
    async def expired(self, now: datetime, limit: int = 100) -> tuple[Reservation, ...]:
        """Pending reservations past their expiry, locked for the caller."""


class Ledger(ABC):
    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[LedgerTransaction]: ...


class _InMemoryTransaction(LedgerTransaction):
    def __init__(
        self, rows: dict[CounterKey, Counter], reservations: dict[str, Reservation]
    ) -> None:
        self._rows = rows
        self._reservations = reservations

    async def get(self, key: CounterKey) -> Counter:
        return self._rows.get(key, Counter())

    async def set(self, key: CounterKey, counter: Counter) -> None:
        self._rows[key] = counter

    async def peek(self, key: CounterKey) -> Counter:
        return self._rows.get(key, Counter())

    async def keys(self) -> Iterable[CounterKey]:
        return tuple(self._rows)

    async def add(self, reservation: Reservation) -> Reservation:
        for existing in self._reservations.values():
            if existing.request_id == reservation.request_id:
                return existing
        self._reservations[reservation.id] = reservation
        return reservation

    async def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self._reservations.get(reservation_id)

    async def get_reservation_by_request(self, request_id: str) -> Reservation | None:
        for reservation in self._reservations.values():
            if reservation.request_id == request_id:
                return reservation
        return None

    async def claim(self, reservation_id: str, state: str) -> Reservation | None:
        reservation = self._reservations.get(reservation_id)
        if reservation is None or reservation.state != "pending":
            return None
        claimed = replace(reservation, state=state)
        self._reservations[reservation_id] = claimed
        return claimed

    async def expired(self, now: datetime, limit: int = 100) -> tuple[Reservation, ...]:
        due = [
            reservation
            for reservation in self._reservations.values()
            if reservation.state == "pending" and reservation.expires_at <= now
        ]
        return tuple(sorted(due, key=lambda item: item.expires_at)[:limit])


class InMemoryLedger(Ledger):
    """A process-local ledger that serialises transactions with one lock."""

    def __init__(self) -> None:
        self._rows: dict[CounterKey, Counter] = {}
        self._reservations: dict[str, Reservation] = {}
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[LedgerTransaction]:
        async with self._lock:
            yield _InMemoryTransaction(self._rows, self._reservations)

    def snapshot(self) -> dict[CounterKey, Counter]:
        """A copy for assertions. Not safe under a concurrent transaction."""
        return dict(self._rows)

    def reservations(self) -> tuple[Reservation, ...]:
        return tuple(self._reservations.values())
