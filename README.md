# Firebrief

Cited answers to UK fire safety guidance questions, with enterprise controls.

> **Status: core answer engine built and tested; no API or UI yet.**
> Ingestion, retrieval, citation verification, refusals, budgets, tenant isolation and PII
> redaction exist as a tested Python library. There is no HTTP API, web UI, audit log or
> live evaluation yet, and nothing is deployed. See [Roadmap](#roadmap).
>
> **Firebrief records and cites. It does not replace a competent person.** Nothing here should
> be used to make a fire safety decision.

## What it does

Firebrief answers a question about UK fire safety guidance in one of two ways:

- **an answer in which every claim quotes the guidance and the quote is checked** against the
  source text before it is shown, or
- **a refusal with a reason**: no relevant guidance was found, the guidance does not cover the
  question, the answer could not be verified, the usage budget was reached, or the model was
  unavailable.

An answer that cannot be verified is never shown. Withholding is a normal outcome, not an
error.

## How an answer is produced

1. **Redact.** Emails, phone numbers, postcodes, National Insurance numbers and Luhn-valid card
   numbers are removed from the question before it leaves the process. The redacted question is
   what is embedded, sent to the model and kept on the result
   ([ADR 0008](docs/adr/0008-redacted-question-is-what-is-stored.md)).
2. **Retrieve.** Hybrid search over the current edition of each document: exact cosine
   similarity over stored embeddings plus Postgres full-text search, combined with Reciprocal
   Rank Fusion. Each result carries its vector rank, text rank, edition and source.
3. **Reserve budget.** The worst-case cost of the model call is reserved against organisation,
   team and user limits before the call is made, then settled at the exact usage or released if
   the call fails ([ADR 0002](docs/adr/0002-estimate-reserve-settle.md)). If the budget service
   itself fails, the request fails closed ([ADR 0007](docs/adr/0007-budget-failures-fail-closed.md)).
4. **Draft.** The model receives numbered, delimited sources and the question, and must quote
   the source for every claim or reply that the evidence is insufficient. Anthropic and OpenAI
   sit behind one interface, with retries, backoff and failover.
5. **Verify.** Each quote must exist in the source it cites (normalised for case, whitespace and
   typography, with a minimum length), and a judge model must agree that the quote supports the
   claim. Judge errors withhold the answer.
6. **Return** the verified answer with its evidence, or a refusal with its reason, usage and
   request ID.

## Corpus

Publicly available government guidance only, reused under the Open Government Licence. What is in
the corpus is decided by a reviewed manifest, [`corpus/sources.toml`](corpus/sources.toml), which
records each document's licence, edition and effective date. Ingestion refuses anything not listed.

- **HTML guidance only for now.** Approved Document B is published as a PDF and is out of scope
  until a layout-aware PDF pipeline exists ([ADR 0004](docs/adr/0004-pdf-guidance-is-out-of-scope-for-now.md)).
- **British Standards are excluded**: they are copyrighted.
- **Every edition is kept.** Document versions, sections and chunks are append-only, enforced by
  database triggers, so an old answer can always be traced to the text it cited
  ([ADR 0003](docs/adr/0003-corpus-append-only-and-writer-role.md)).

## Engineering overview

| Area | What exists | Where |
|---|---|---|
| Tenant isolation | Postgres row-level security with `FORCE`, a per-transaction tenant setting, composite foreign keys so rows can't reference another tenant, a start-up check that the app role cannot bypass RLS, and an invariant test that every table is tenant-scoped or explicitly reviewed | `db/`, `migrations/`, `tests/db/test_rls.py` |
| Budgets | Estimate, reserve, settle or release; integer micro-unit money; hierarchical limits; property and concurrency tests | `budget/`, `tests/budget/` |
| Model access | Provider-agnostic adapters, error classification, router with retries, backoff and failover, and a fake provider so tests need no API keys | `llm/` |
| Ingestion | GOV.UK Content API adapter, structure-aware HTML parsing (headings, tables, intro text), content-hashed versions, current-edition selection | `ingest/` |
| Chunks and embeddings | Section-linked chunks with offsets; embedding model and dimensions recorded per set | `ingest/chunk.py`, `ingest/embed.py` |
| Retrieval | Hybrid vector and full-text search with RRF, current edition only | `retrieval/` |
| Answers | Prompt contract, citation verifier, judge, refusal reasons and messages | `answer/` |
| Guardrails | Pattern-based PII redaction; findings record kind and count, never the value | `guardrails/` |

Pattern redaction does not detect names, free-text addresses or obfuscated forms
("ada [at] example [dot] com"). That is a stated limit, not an oversight.

## Quality and evaluation

There are **no evaluation results to report yet.**

- `make eval-retrieval` runs recall@3 over a six-question set with a bag-of-words embedder. It
  checks that retrieval is wired correctly; it is not a quality measurement.
- The evaluation harness (about 120 labelled questions, replayed on every pull request and run
  live nightly, reporting answer correctness, citation precision, correct refusals, latency and
  cost) is on the roadmap and not built.
- Retrieval applies no similarity floor yet, so an unrelated question reaches the model and is
  refused after the call rather than before it. Calibrating a per-model floor is a task for the
  evaluation harness ([ADR 0006](docs/adr/0006-no-similarity-floor-in-retrieval.md)).

## Quickstart

Requires `uv`, Python 3.12 and Docker.

```bash
make setup      # install dependencies from the lockfile
make up         # start local Postgres and Redis (used by the database tests)
make check      # lint, format, types, module boundaries, licences, tests: exactly what CI runs
make help       # list every target
```

Environment variables for local runs are listed in [`.env.example`](.env.example).

Other useful targets:

```bash
make eval-retrieval   # retrieval smoke gate (recall@3)
make db-roundtrip     # migrate up, down, up, then check for model drift
make docker-smoke     # build the image, check it imports and does not run as root
make secrets          # scan the full git history for secrets
```

## Run it locally

End to end, from a clean checkout. Two terminals: one for the API, one for the web UI.

```bash
# 1. Database and cache
make up                      # Postgres on :55433, Redis on :56380

# 2. Database and workspace (creates firebrief_dev, migrates it, seeds it)
make dev-setup

# 3. API (terminal one) — http://127.0.0.1:8010
make api

# 4. Web UI (terminal two) — http://127.0.0.1:5173
make web-install             # first time only
make web
```

Then open the sign-in URL that `make seed` printed:

```
http://127.0.0.1:5173/sign-in?tenant=018f0000-0000-7000-8000-0000000000aa
```

Enter the seeded address, `dev@firebrief.local`.

**Where the link goes depends on one variable.** With `RESEND_API_KEY` set, the link is
emailed by Resend; without it, the API prints the link to the terminal where `make api` runs:

```bash
RESEND_API_KEY=re_... FIREBRIEF_EMAIL_FROM='Firebrief <sign-in@yourdomain>' make api
```

`onboarding@resend.dev` (the default sender) only delivers to the Resend account owner, so
use a verified domain for anyone else. In production the API refuses to start without
`RESEND_API_KEY`: printing sign-in links to a log is not a delivery mechanism.

If Resend rejects a message, the endpoint still returns the same `202`; the failure is
logged, because whether delivery failed must not reveal whether an address exists.

Ask a question such as **"How long can a dead end be?"**. The web UI proxies `/v1` to the
API, so the `HttpOnly` session cookie works on one origin.

### What the local run actually does

Two parts are deliberately stubbed, and they change what you are looking at:

| Piece | Local default | Consequence |
|---|---|---|
| Model provider | `ExtractiveProvider` (no key) | Answers quote the first sentence of the top-ranked source. It cannot reason, so a question about dead ends may quote a different section that shares words. Set `FIREBRIEF_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` for a real model |
| Support judge | `FixedJudge` | The verifier checks that every quote exists in the source, but not that it supports the claim. The support judge is not built yet |

The rest is real: row-level security, the budget ledger, rate limits, citation offsets and
refusals all behave as they do in production. The corpus is
[`config/dev-corpus.html`](config/dev-corpus.html), a four-section demonstration sample, not
the reviewed GOV.UK corpus — so treat the content of any answer here as a plumbing test.

To use a real model:

```bash
FIREBRIEF_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... make api
```

The database URL defaults to the **runtime role**, `firebrief_app`. The application refuses
to start as the owner, because a superuser can drop the row-level-security policies; if you
point `FIREBRIEF_DATABASE_URL` at the owner you will see exactly that error.

Development runs against `firebrief_dev`. The test suite runs against `firebrief_test` and
**truncates it between tests**, so the dev server refuses to start on a `*_test` database:
otherwise every `make check` would quietly delete the workspace you are signed into.

### Running the web tests

```bash
make web-test                # typecheck + Vitest + jest-axe
cd web && npx playwright install chromium && npm run e2e
cd web && npm run build      # static pages, sitemap, robots
```

## Repository layout

```
src/firebrief/
  answer/      # prompt, citation verifier, judge, refusals, pipeline
  auth/        # magic-link auth (in progress)
  budget/      # pricing, estimates, reservations, ledger, budget service
  db/          # models, sessions, tenant context, role checks
  guardrails/  # PII redaction
  ingest/      # manifest, sources, parsing, versions, chunking, embeddings
  llm/         # provider interface, Anthropic and OpenAI adapters, router, fake provider
  retrieval/   # hybrid search and rank fusion
migrations/    # Alembic migrations, including RLS policies, grants and append-only triggers
corpus/        # the reviewed source manifest
config/        # pricing tables (integer micros per million tokens)
evals/         # evaluation sets
docs/adr/      # architecture decision records
docs/features/ # the plan for each feature, written before it was built
scripts/       # licence check, secret scan, clean-clone check, canary
tests/         # unit, property, concurrency and database tests
```

## Decisions

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-repository-and-toolchain.md) | Repository and toolchain |
| [0002](docs/adr/0002-estimate-reserve-settle.md) | Estimate, reserve, settle for every model call |
| [0003](docs/adr/0003-corpus-append-only-and-writer-role.md) | The corpus is append-only, written by a dedicated role |
| [0004](docs/adr/0004-pdf-guidance-is-out-of-scope-for-now.md) | PDF guidance is out of scope for now |
| [0005](docs/adr/0005-exact-vector-search-before-pgvector.md) | Exact vector search before pgvector |
| [0006](docs/adr/0006-no-similarity-floor-in-retrieval.md) | No similarity floor in retrieval |
| [0007](docs/adr/0007-budget-failures-fail-closed.md) | Budget failures fail closed |
| [0008](docs/adr/0008-redacted-question-is-what-is-stored.md) | The redacted question is what is stored |

## Roadmap

The full plan, in dependency order, is in [`docs/ROADMAP.md`](docs/ROADMAP.md). Next up:

- **Auth**: magic-link sign-in with hashed, single-use, expiring links (in progress), with an
  OIDC adapter behind the same interface later
- **Audit log**: append-only record of every question, the evidence and the outcome
- **Evaluation harness**: the labelled question set and results table described above
- **API and web UI**: ask a question, see the answer with its citations or the refusal
- **Durable budgets, rate limiting, observability and deployment**

## How this is being built

Feature by feature, test first. Each feature has a written plan in `docs/features/`, is built on
its own branch, and is merged by pull request after review. The budget and LLM modules were
prototyped before this repository was initialised, so the history begins at the foundation rather
than at the first line of code ([ADR 0001](docs/adr/0001-repository-and-toolchain.md)).

**Use of AI tools.** AI assistants were used for design discussion, for reviewing pull requests,
and to prototype the budget and LLM modules. Every change was reviewed, tested and merged by the
author. *(Edit this paragraph so it describes your own use accurately.)*

## Licence

Functional Source License, Version 1.1, Apache 2.0 Future License (FSL-1.1-ALv2). You may read,
run and modify the code; you may not use it to provide a competing commercial service. Two years
after each release, that release becomes available under Apache 2.0. See [LICENSE](LICENSE).
