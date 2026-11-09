# Firebrief

Cited answers to UK fire safety guidance questions, with enterprise controls.

> **Status: foundation (F0/F1).** The budget and LLM layers exist and are tested. Ingestion,
> retrieval, the answer pipeline and the web UI are not built yet. Nothing here should be used to
> make a fire safety decision.

Firebrief answers questions about UK fire safety guidance and shows the passage each claim comes
from — or says plainly that the guidance does not cover the question. Answers are bounded by
per-organisation, per-team and per-user token budgets, every question is audited, and nothing is
sent to a model before PII is redacted.

Sources are publicly available government guidance only (Approved Document B, the Regulatory
Reform (Fire Safety) Order guides, Building Safety Act 2022 guidance and Fire Safety (England)
Regulations 2022 guidance), reused under the Open Government Licence with attribution. British
Standards are copyrighted and excluded.

**Firebrief records and cites. It does not replace a competent person.** The output is a pointer
to the source, not professional fire safety advice.

## Quickstart

Requires `uv` and Python 3.12.

```bash
make setup      # install dependencies from the lockfile
make check      # lint, format, types, boundaries, licences, tests — exactly what CI runs
make help       # list every target
```

`make check` should be green on a fresh clone in under five minutes.

## Layout

```
src/firebrief/
  budget/    # pricing, token estimates, reservations, ledger, budget service
  llm/       # provider interface, Anthropic + OpenAI adapters, router, fake provider
config/      # pricing tables (integer micros per million tokens)
evals/       # evaluation harnesses and question sets
tests/       # unit, property and concurrency tests
docs/adr/    # architecture decision records
```

## How this is being built

Feature by feature, test first, with the plan and the review recorded in the repository. The
budget and LLM modules were prototyped before this repository was initialised, so the history
begins at the foundation rather than at the first line of code. That is stated here rather than
smoothed over. See `docs/adr/0001-repository-and-toolchain.md`.

## Licence

Functional Source License, Version 1.1, Apache 2.0 Future License (FSL-1.1-ALv2). You may read,
run and modify the code; you may not use it to provide a competing commercial service. After two
years each release converts to Apache 2.0. See [LICENSE](LICENSE).
