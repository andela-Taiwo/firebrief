# budget-durability: a restart must not forget what was spent

**Status:** In progress · **Branch:** `feat/budget-ledger`
**Depends on:** `answer-pipeline` · **Unblocks:** a real deployment

## Goal

The budget is the promise that a customer cannot overspend. It lived in process memory, so
a restart forgot every charge and a second instance disagreed with the first. The counters
and the reservations are now rows.

## Scope

**In**
- `budget_counters`: one row per (scope, period, period start), holding reserved and spent.
- `budget_reservations`: one row per request, so a reservation survives a restart and can
  still be settled or swept.
- `PostgresLedger` and `PostgresReservationStore` behind the existing protocols.
- The budget service becomes asynchronous, because a Postgres round trip inside a sync
  method would block the event loop.

**Out (and where it goes)**
- Tenant scoping for the ledger: it is keyed by opaque scope ids and has no tenant column,
  so it is on the reviewed-global list. Whether that changes is a decision for the RBAC
  feature, and it is recorded here rather than assumed.
- A scheduled sweeper: `sweep()` exists and is tested, but nothing calls it on a timer yet.
- Redis as a fast path in front of the counters. Postgres is the authoritative store first;
  a cache can come later without changing the API.

## Decisions & trade-offs

### D1. Row locks, not optimistic retries
A reservation reads and updates the counters for its scopes inside one transaction. `get`
creates the row (`on conflict do nothing`) before `select ... for update`, because a lock
cannot be taken on a row that does not exist yet — the first concurrency test failed for
exactly that reason, with two first-time reservations both admitted.

### D2. The reservation is written inside the same transaction as the counters
A crash between them would leave capacity held with no record, or a record with no
capacity. Both are written in the ledger transaction.

### D3. No DELETE grant
A reservation is a record of what was charged. It can be settled, released or swept, never
removed, so the ledger remains an audit trail.

### D4. Async all the way
`Ledger` and `ReservationStore` became async, and the service followed. The alternative — a
sync ledger called from async code — would block the event loop for a network round trip.

## Acceptance criteria

1. Spend recorded by one service instance is seen by another.
2. A reservation can be settled after a restart.
3. An abandoned reservation is swept and its capacity returned.
4. Two concurrent first-time reservations cannot both fit into one slot.
5. The counters never go negative, enforced by the database.
6. The budget tables are on the reviewed-global list with a reason.

## Test plan

Both implementations satisfy the same service tests. The Postgres pair is tested for
durability, settlement after a restart, sweeping, and a concurrent race for the last slot.

Canaries: skip the row-creation before locking; make reads ignore stored spend; stop the
sweep releasing.

## Risks

| Risk | Mitigation |
|---|---|
| A sweep that never runs leaks capacity | `sweep()` is tested; the scheduled job is recorded as open |
| Row locks under load | One row per scope and period; contention is per customer, not global |
| The ledger is not tenant-scoped | Recorded as an open decision for RBAC, not silently accepted |

## Effort

3 dev-days, one PR.
