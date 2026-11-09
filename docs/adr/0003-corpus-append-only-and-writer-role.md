# ADR 0003 — Append-only is enforced for the runtime role and below

**Status:** Accepted · **Date:** 2026-11-09

## Context

Versions and sections are append-only by trigger, so a correction is a new version rather than
an edit. But a PostgreSQL table owner can `TRUNCATE`, `ALTER TABLE ... DISABLE TRIGGER`, or drop
the trigger. The claim "nothing can change history" is therefore true only for roles that do not
own the table.

Ingestion currently writes as the owner, because it needs INSERT on all three corpus tables.

## Decision

State the limit precisely rather than overclaim:

- The **runtime role** has `SELECT` only on `documents`, `document_versions` and `sections`. It
  cannot write, and it does not own them (asserted by `assert_safe_database_role`).
- The **owner** writes, and could therefore defeat the trigger. That is a deliberate,
  documented bypass, not an accident.
- The next step is a dedicated `firebrief_ingest` role with INSERT only and no TRUNCATE, so the
  writer cannot destroy history either. Until then, ingestion is an operator command run by a
  human, not a service.

## Consequences

- An audit of "who could have changed a version" must include the owner.
- The trigger protects against application bugs and compromised request paths, which is the
  realistic threat, not against a malicious DBA.
- Migration, backup and restore tooling run as the owner and are outside this guarantee.

## Revisit when

A separate ingest role is introduced (F3.1), or the corpus is written by a long-running service
rather than an operator command.
