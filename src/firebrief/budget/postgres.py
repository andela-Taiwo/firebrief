"""A durable ledger.

Counters and reservations share one transaction, because they must commit together: a
reservation without its capacity leaks nothing to sweep, and capacity without a
reservation leaks nothing to settle.

Every state change is one conditional `UPDATE ... WHERE state = 'pending' RETURNING`, so a
late settle racing the sweeper — or two sweepers on two instances — cannot both win.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from datetime import date, datetime

from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from firebrief.budget.ledger import Counter, CounterKey, Ledger, LedgerTransaction, Reservation
from firebrief.budget.limits import Period, ScopeType
from firebrief.budget.money import Money

ENSURE = text(
    """
    insert into budget_counters (scope_type, scope_id, period, period_start, reserved, spent)
    values (:scope_type, :scope_id, :period, :period_start, 0, 0)
    on conflict (scope_type, scope_id, period, period_start) do nothing
    """
)

UPSERT = text(
    """
    insert into budget_counters (scope_type, scope_id, period, period_start, reserved, spent)
    values (:scope_type, :scope_id, :period, :period_start, :reserved, :spent)
    on conflict (scope_type, scope_id, period, period_start)
    do update set reserved = excluded.reserved, spent = excluded.spent
    """
)

CLAIM = text(
    """
    update budget_reservations set state = :state
    where id = :id and state = 'pending'
    returning *
    """
)

EXPIRED = text(
    """
    select * from budget_reservations
    where state = 'pending' and expires_at <= :now
    order by expires_at
    limit :limit
    for update skip locked
    """
)


class _PostgresTransaction(LedgerTransaction):
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def get(self, key: CounterKey) -> Counter:
        # A lock cannot be taken on a row that does not exist, so create it first.
        await self._connection.execute(ENSURE, _key_params(key))
        row = (
            await self._connection.execute(
                text(
                    "select reserved, spent from budget_counters "
                    "where scope_type = :scope_type and scope_id = :scope_id "
                    "and period = :period and period_start = :period_start for update"
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
        return tuple(CounterKey(ScopeType(row[0]), row[1], Period(row[2]), row[3]) for row in rows)

    async def add(self, reservation: Reservation) -> Reservation:
        await self._connection.execute(
            text(
                "insert into budget_reservations "
                "(id, request_id, model, amount, keys, created_at, expires_at, state) "
                "values (:id, :request_id, :model, :amount, cast(:keys as jsonb), "
                ":created_at, :expires_at, "
                "'pending') on conflict (request_id) do nothing"
            ),
            {
                "id": uuid.UUID(reservation.id),
                "request_id": reservation.request_id,
                "model": reservation.model,
                "amount": int(reservation.amount),
                "keys": json.dumps(_keys_payload(reservation.keys)),
                "created_at": reservation.created_at,
                "expires_at": reservation.expires_at,
            },
        )
        existing = (
            await self._connection.execute(
                text("select * from budget_reservations where request_id = :request_id"),
                {"request_id": reservation.request_id},
            )
        ).first()
        assert existing is not None
        return _row_to_reservation(existing)

    async def get_reservation(self, reservation_id: str) -> Reservation | None:
        row = (
            await self._connection.execute(
                text("select * from budget_reservations where id = :id"),
                {"id": uuid.UUID(reservation_id)},
            )
        ).first()
        return _row_to_reservation(row) if row is not None else None

    async def claim(self, reservation_id: str, state: str) -> Reservation | None:
        row = (
            await self._connection.execute(CLAIM, {"state": state, "id": uuid.UUID(reservation_id)})
        ).first()
        return _row_to_reservation(row) if row is not None else None

    async def expired(self, now: datetime, limit: int = 100) -> tuple[Reservation, ...]:
        rows = (await self._connection.execute(EXPIRED, {"now": now, "limit": limit})).all()
        return tuple(_row_to_reservation(row) for row in rows)


def _key_params(key: CounterKey) -> dict[str, object]:
    return {
        "scope_type": key.scope_type.value,
        "scope_id": key.scope_id,
        "period": key.period.value,
        "period_start": key.period_start,
    }


def _keys_payload(keys: tuple[CounterKey, ...]) -> list[dict[str, str]]:
    return [
        {
            "scope_type": key.scope_type.value,
            "scope_id": key.scope_id,
            "period": key.period.value,
            "period_start": key.period_start.isoformat(),
        }
        for key in keys
    ]


def _row_to_reservation(row) -> Reservation:  # type: ignore[no-untyped-def]
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
        state=row.state,
    )


class PostgresLedger(Ledger):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[LedgerTransaction]:
        async with self._engine.begin() as connection:
            yield _PostgresTransaction(connection)


def reservation_table() -> Table:
    from firebrief.db.models import BudgetReservation

    return BudgetReservation.__table__  # type: ignore[return-value]
