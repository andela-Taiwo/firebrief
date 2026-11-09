"""The counter store behind the budget service.

The ledger holds, per (scope, period, period start), the amount currently
reserved and the amount actually spent. Reservations are applied to every level
of the hierarchy in a single transaction, so a request is either reserved at
org, team and user level or at none of them.

`InMemoryLedger` is the reference implementation used by the tests. The
Postgres-backed ledger arrives with the durability feature (F11); the protocol
is deliberately narrow so that swap is a configuration change, not a rewrite.
"""

from __future__ import annotations

import threading
from collections.abc import Generator, Iterable
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from firebrief.budget.limits import Period, ScopeType
from firebrief.budget.money import Money


@dataclass(frozen=True, slots=True)
class CounterKey:
    scope_type: ScopeType
    scope_id: str
    period: Period
    period_start: date


@dataclass(frozen=True, slots=True)
class Counter:
    reserved: Money = 0
    spent: Money = 0

    @property
    def used(self) -> Money:
        return self.reserved + self.spent


class LedgerTransaction(Protocol):
    def get(self, key: CounterKey) -> Counter: ...

    def set(self, key: CounterKey, counter: Counter) -> None: ...

    def keys(self) -> Iterable[CounterKey]: ...


class Ledger(Protocol):
    def transaction(self) -> AbstractContextManager[LedgerTransaction]: ...


class _InMemoryTransaction:
    def __init__(self, rows: dict[CounterKey, Counter]) -> None:
        self._rows = rows

    def get(self, key: CounterKey) -> Counter:
        return self._rows.get(key, Counter())

    def set(self, key: CounterKey, counter: Counter) -> None:
        self._rows[key] = counter

    def keys(self) -> Iterable[CounterKey]:
        return tuple(self._rows)


class InMemoryLedger:
    """A process-local ledger that serialises transactions with one lock."""

    def __init__(self) -> None:
        self._rows: dict[CounterKey, Counter] = {}
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Generator[_InMemoryTransaction]:
        with self._lock:
            yield _InMemoryTransaction(self._rows)

    def snapshot(self) -> dict[CounterKey, Counter]:
        with self._lock:
            return dict(self._rows)
