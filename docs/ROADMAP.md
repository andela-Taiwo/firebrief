# Roadmap

Status: Not started · Planning · Awaiting sign-off · In progress · In review · Done

Build order is dependency order, not importance. v1 ships the block up to the cut line.

## Phase 0 — Foundation

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `repo-foundation` | Guard rails: locked installs, single `make check`, secret scan, licence gate, boundaries, container | — | In progress |
| `adopt-budget-and-llm` | Reservation ledger and provider router, tested | repo-foundation | In progress |

## Phase 1 — Corpus and tenancy

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `tenant-isolation` | RLS with FORCE, per-transaction tenant, start-up role check, invariant test | repo-foundation | In review |
| `corpus-ingestion` | Snapshot GOV.UK guidance with licence, edition and effective dates | tenant-isolation | Not started |
| `chunk-and-embed` | Structure-aware chunks, versioned embeddings | corpus-ingestion | Not started |
| `hybrid-retrieval` | Vector + full-text fusion, recall measured | chunk-and-embed | Not started |
| `context-packing` | Fixed token split with a documented truncation policy | hybrid-retrieval | Not started |

## Phase 2 — Answer quality (critical path)

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `answer-pipeline` | Streaming answer through the single gateway | context-packing | Not started |
| `citation-verifier` | Span existence, then support; withhold on failure | answer-pipeline | Not started |
| `refusal-and-evidence` | Say plainly when the guidance does not cover it | citation-verifier | Not started |
| `eval-harness` | 120 questions; replay on PR, live nightly | citation-verifier | Not started |

## Phase 3 — Money and limits

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `budget-ledger-durability` | Postgres authoritative, Redis a reconciled fast path | adopt-budget-and-llm | Not started |
| `rate-limiter` | Per tenant and user, auth endpoints included | budget-ledger-durability | Not started |
| `semantic-cache` | Tenant-scoped, corpus-version keyed | hybrid-retrieval | Not started |

## Phase 4 — Governance

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `auth` | Magic link, OIDC adapter behind the same interface | tenant-isolation | Not started |
| `audit-log` | Trigger-enforced append-only, purge path | tenant-isolation | Not started |
| `guardrails` | Untrusted content as data, PII redaction | answer-pipeline | Not started |
| `rbac` | admin ⊇ manager ⊇ viewer, role matrix tests | auth | Not started |

## Phase 5 — Surface

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `api-hardening` | problem+json, request IDs, limits, generated types | auth | Not started |
| `web-ui` | Ask, answer with citations, refusal state | api-hardening | Not started |
| `observability` | Structured logs, spans, cost and latency metrics | answer-pipeline | Not started |

## Phase 6 — Ship

| Feature | Goal | Depends on | Status |
|---|---|---|---|
| `deployment` | Migrations pre-deploy, health checks, demo spend cap | api-hardening | Not started |
| `docs-and-adrs` | README to green in five minutes; eval table | all | Not started |
| `demo` | Public demo with a hard budget | deployment | Not started |
