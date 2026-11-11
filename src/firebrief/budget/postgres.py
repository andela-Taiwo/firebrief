"""A durable ledger and reservation store.

The counters are one row per (scope, period, period start); a reservation is one row per
request. Writes take a row lock, so two concurrent reservations at the same key serialise
and cannot both fit under a limit that only has room for one.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy import Table, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from firebrief.budget.ledger import Counter, CounterKey
from firebrief.budget.money import Money
from firebrief.budget.service import Reservation, ReservationState

UPSERT = text(
    """
    insert into budget_counters (scope_type, scope_id, period, period_start, reserved, spent)
    values (:scope_type, :scope_id, :period, :period_start, :reserved, :spent)
    on conflict (scope_type, scope_id, period, period_start)
    do update set reserved = excluded.reserved, spent = excluded.spent
    """
)


class _PostgresTransaction:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def get(self, key: CounterKey) -> Counter:
        # `FOR UPDATE` locks rows that exist; a first-time reservation would race with
        # another first-time reservation. Create the row (or wait for the other
        # transaction's insert) before locking it.
        await self._connection.execute(
            text(
                "insert into budget_counters "
                "(scope_type, scope_id, period, period_start, reserved, spent) "
                "values (:scope_type, :scope_id, :period, :period_start, 0, 0) "
                "on conflict (scope_type, scope_id, period, period_start) do nothing"
            ),
            _key_params(key),
        )
        row = (
            await self._connection.execute(
                text(
                    "select reserved, spent from budget_counters "
                    "where scope_type = :scope_type and scope_id = :scope_id "
                    "and period = :period and period_start = :period_start "
                    "for update"
                ),
                _key_params(key),
            )
        ).first()
        if row is None:
            return Counter()
        return Counter(reserved=Money(int(row[0])), spent=Money(int(row[1])))

    async def set(self, key: CounterKey, counter: Counter) -> None:
        await self._connection.execute(
            UPSERT,
            {
                **_key_params(key),
                "reserved": int(counter.reserved),
                "spent": int(counter.spent),
            },
        )

    async def keys(self) -> Iterable[CounterKey]:
        rows = (
            await self._connection.execute(
                text("select scope_type, scope_id, period, period_start from budget_counters")
            )
        ).all()
        from firebrief.budget.limits import Period, ScopeType

        return tuple(CounterKey(ScopeType(row[0]), row[1], Period(row[2]), row[3]) for row in rows)


def _key_params(key: CounterKey) -> dict[str, object]:
    return {
        "scope_type": key.scope_type.value,
        "scope_id": key.scope_id,
        "period": key.period.value,
        "period_start": key.period_start,
    }


class PostgresLedger:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[_PostgresTransaction]:
        async with self._engine.begin() as connection:
            yield _PostgresTransaction(connection)


class PostgresReservationStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def add(self, reservation: Reservation) -> None:
        async with self._engine.begin() as connection:
            statement = insert(_reservations()).values(
                id=uuid.UUID(reservation.id),
                request_id=reservation.request_id,
                model=reservation.model,
                amount=int(reservation.amount),
                keys=[_key_payload(key) for key in reservation.keys],
                created_at=reservation.created_at,
                expires_at=reservation.expires_at,
                state=reservation.state.value,
            )
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "state": statement.excluded.state,
                        "amount": statement.excluded.amount,
                    },
                )
            )

    async def get(self, reservation_id: str) -> Reservation | None:
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    _reservations()
                    .select()
                    .where(_reservations().c.id == uuid.UUID(reservation_id))
                )
            ).first()
        return _reservation_from_row(row) if row is not None else None

    async def pending(self) -> tuple[Reservation, ...]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    _reservations()
                    .select()
                    .where(_reservations().c.state == ReservationState.PENDING.value)
                )
            ).all()
        return tuple(_reservation_from_row(row) for row in rows)


def _reservations() -> Table:
    from firebrief.db.models import BudgetReservation

    return cast(Table, BudgetReservation.__table__)


def _key_payload(key: CounterKey) -> dict[str, str]:
    return {
        "scope_type": key.scope_type.value,
        "scope_id": key.scope_id,
        "period": key.period.value,
        "period_start": key.period_start.isoformat(),
    }


def _reservation_from_row(row) -> Reservation:  # type: ignore[no-untyped-def]
    from datetime import date

    from firebrief.budget.limits import Period, ScopeType

    keys = tuple(
        CounterKey(
            ScopeType(item["scope_type"]),
            item["scope_id"],
            Period(item["period"]),
            date.fromisoformat(item["period_start"]),
        )
        for item in row.keys
    )
    return Reservation(
        id=str(row.id),
        request_id=row.request_id,
        model=row.model,
        amount=Money(int(row.amount)),
        keys=keys,
        created_at=row.created_at,
        expires_at=row.expires_at,
        state=ReservationState(row.state),
    )


def reservation_rows(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    """A helper for tests that need to look at the rows directly."""
    return PostgresReservationStore(engine)
