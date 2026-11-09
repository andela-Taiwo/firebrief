# ADR 0001 — Repository, toolchain and licence

**Status:** Accepted · **Date:** 2026-11-09

## Context

The design document describes the product and the decisions taken, but this repository did not
exist. Two decisions had to be made immediately because everything else depends on them: what the
toolchain is, and what the licence is.

## Decision

**Toolchain.** uv with a committed `uv.lock`, installed with `uv sync --locked`; Ruff for lint and
format; pyright in `standard` mode with `reportDeprecated = "error"`; pytest with
`filterwarnings = ["error"]`; import-linter for module boundaries; gitleaks for secrets; an
exact-match licence allowlist.

**One entry point.** `make check` runs exactly what CI runs. There are no CI-only steps.

**Licence.** FSL-1.1-ALv2. Source-available now, Apache-2.0 after two years per release.

## Alternatives considered

| Option | Why not |
|---|---|
| Apache-2.0 | A competitor could host the product commercially, which is exactly the free-riding the product cannot afford. |
| BSL 1.1 | Same intent, but a bespoke change date and a longer grant of future licence; FSL is the clearer, more recent form of the same idea. |
| Proprietary, no source | Loses the "built in the open" credibility that is part of the project's value. |
| Poetry / pip-tools | Slower, weaker lockfile enforcement, and `uv --locked` is the flag that actually fails on a stale lock. |

## Consequences

- `uv.lock` must be committed and regenerated whenever dependencies change; CI fails otherwise.
- A new dependency needs a licence review before it can merge.
- The FSL is not OSI-approved. That is a feature here, but it must be stated plainly in the README
  and any distribution.

## Open question

Which legal entity holds the copyright? Currently an individual; §14.3 of the playbook recommends
a company before any revenue.
