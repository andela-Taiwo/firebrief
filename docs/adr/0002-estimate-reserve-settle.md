# ADR 0002 — Estimate, reserve, settle

**Status:** Accepted · **Date:** 2026-11-09

## Context

Several requests run concurrently against the same monthly budget. Checking the remaining balance
before a call and subtracting after it is a race: N concurrent requests all read the old balance
and all proceed. The overspend is not theoretical — it is proportional to concurrency.

## Decision

A request **reserves its worst-case cost** at every level of the hierarchy (organisation, team,
user), in a single transaction, before the model is called. When the call completes the reservation
is **settled** at the provider's exact usage, and the difference is returned. If the call fails the
reservation is **released**. Reservations expire, and a sweep releases any that the holder never
settled.

All-or-nothing: a request that cannot reserve at every level reserves at none of them.

Money is an integer number of micro-units and every charge is rounded **up**, once.

## Alternatives considered

| Option | Why not |
|---|---|
| Check-then-deduct | Races; overspends by the concurrency factor. |
| Reserve after the call | The spend has already happened; the limit cannot prevent anything. |
| Optimistic versioning with retries | Correct, but a reservation under contention would spin instead of failing fast. The ledger lock is cheaper and the critical section is tiny. |
| Floats for money | Drift and rounding disputes. Integer micros, rounded up, is auditable. |

## Consequences

- The ledger is the source of truth for spend, so it must be durable. The in-memory ledger is a
  reference implementation for tests; the Postgres ledger is F11, and Redis is at most a fast path.
- A crashed process leaves a reservation behind. The TTL sweep is not optional.
- Settling more than was reserved is possible when a provider reports more output than requested.
  The charge is clamped to the reservation and the overage is recorded, so the invariant
  `spent + reserved <= limit` cannot be broken by a misbehaving provider.
