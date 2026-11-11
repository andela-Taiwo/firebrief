# ADR 0009 — Refusals are answers; capacity conditions are not

**Status:** Accepted · **Date:** 2026-11-11

## Context

Every answer can end in a refusal: no sources, insufficient evidence, an unverifiable claim.
Those are outcomes of answering. Two other outcomes are not about the question at all: the
budget is exhausted, or the model or ledger is unavailable.

Returning all of them as `200` was the original choice, for one reason: a refusal is a real
answer and the UI should render it, not treat it as a failure.

## Decision

- **Refusals about the answer** — `no_sources`, `insufficient_evidence`, `unverified`,
  `truncated` — are `200` with a reason, a message and the evidence considered.
- **`budget_exhausted` is `429`.**
- **`budget_unavailable` and `model_unavailable` are `503`.**

The body shape is identical either way.

## Why

A `200` tells a monitoring system, a retry policy and a browser that everything is fine.
A user who has run out of budget is not getting an answer, and a model outage is not an
answer either. Those two need to be distinguishable by machines, not only by reading a
string inside a `200`.

Keeping the answer-level refusals at `200` still holds: nothing has failed, the product
simply declined to invent an answer. That distinction is the point of the feature.

## Consequences

- The UI must handle three statuses, not one, and can show "limit reached" from the
  response code alone.
- `Retry-After` is not sent yet: the reset time is in the refusal details as text, and a
  machine-readable header needs the budget service to expose it. Recorded as a follow-up.

## Revisit when

Retries are automated by clients, at which point the reset time must become a header
rather than a sentence.
