# ADR 0007 — Budget failures fail closed

**Status:** Accepted · **Date:** 2026-11-10

## Context

Before a model call, the pipeline reserves the request's worst-case cost. The reservation
can fail because the limit is reached, or because the ledger itself is unavailable.

Failing open would keep the product working during an outage: the answer is produced and
the spend is not recorded. Failing closed refuses the question.

## Decision

**Fail closed.** If the budget service raises, the question is refused with
`BUDGET_EXHAUSTED` and a detail saying the budget service was unavailable. Nothing is
attempted, so nothing is spent unrecorded.

Bookkeeping failures *after* the call — settling or releasing — are logged and swallowed.
An answer that was produced and verified is still shown; its cost is recovered by the
periodic reconciliation, not by withholding the answer.

## Why

The budget is the only control that bounds spend for a customer. A control that silently
stops applying during an outage is not a control, and the failure is invisible exactly
when it matters. Refusing is loud, recoverable, and reported to the user as a temporary
condition rather than as a wrong answer.

## Consequences

- A ledger outage stops answering. That is the intended trade.
- Settle and release failures are logged; the ledger may temporarily understate spend.
- The reconciliation sweep is what makes that safe, and it is not built yet. It is
  recorded as a follow-up for the budget durability work (F11).

## Revisit when

The ledger is replicated enough that an outage is not a realistic failure mode.
