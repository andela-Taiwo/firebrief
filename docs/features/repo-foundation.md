# repo-foundation: the guard rails every later feature lands in

**Status:** Awaiting sign-off · **Branch:** `feat/repo-foundation`
**Depends on:** nothing · **Unblocks:** every feature

## Goal

A repository where a second contributor can clone, run `make check`, and get the same result CI
gets — and where the failure modes this project is exposed to (leaked secrets, a copyleft
dependency, a stale lockfile, an import that crosses a module boundary, a warning that becomes a
bug) each fail loudly instead of passing quietly.

## Scope

**In**
- uv workspace with a committed lockfile, installed with `--locked`.
- One entry point: `make check` = exactly what CI runs; `make help` lists targets.
- Ruff (lint + format), pyright `standard` with deprecations as errors, pytest with warnings as
  errors.
- import-linter contract keeping the budget and LLM layers independent.
- gitleaks over the full history, failing when it scanned zero commits.
- Exact-match dependency licence allowlist.
- Multi-stage, non-root Docker image; Compose with Postgres and Redis pinned by digest.
- CI with actions pinned by commit SHA, `contents: read`, `persist-credentials: false`.
- Dependabot, PR template, CONTRIBUTING, `.env.example`, ADRs.

**Out (and where it goes)**
- FastAPI app, database, RLS: F2 onwards.
- pgvector image: F4.
- Postgres-backed budget ledger: F11.

## Decisions & trade-offs

### D1. Adopt the prototyped budget and LLM layers rather than rewrite them
The design document records them as done, but no code existed in the repository (the directory was
empty). They have been implemented here to that specification, in one labelled commit, and the
README says so.

| Option | For | Against |
|---|---|---|
| **Implement to the documented spec (chosen)** | Honest, unblocks F2, the tests prove the behaviour | Not literally "adoption"; the spec's 20 tests became 36 by writing the edge cases explicitly |
| Pretend they were adopted | — | Misrepresents how the work happened |

### D2. Licence: FSL-1.1-ALv2 rather than Apache-2.0
Source-available: readers, researchers and internal users are welcome; a competing hosted product
is not; each release converts to Apache-2.0 after two years. Apache-2.0 alone would let a
competitor host the product.

### D3. uv cache inside the workspace
`UV_CACHE_DIR` defaults to `$(CURDIR)/.uv-cache`. This environment cannot write to `~/.cache/uv`,
and it also keeps the cache out of the global namespace. CI sets its own.

### D4. One image, both stages on the uv base
The uv image already contains Python 3.12, so pinning a second base image would be a second thing
to keep in step. The runtime stage copies only `.venv`, `src` and `config`.

## Acceptance criteria

1. `make setup && make check` is green on a fresh clone.
2. `make check` also green in CI, with the same commands (no CI-only steps).
3. A planted fake secret fails `make secrets`.
4. A secret scan that finds no commits fails rather than passing.
5. An import from `firebrief.budget` to `firebrief.llm` fails `make boundaries`.
6. A GPL-licensed dependency fails `make licenses`.
7. A stale `uv.lock` fails `uv sync --locked`.
8. A deprecated API fails `make types`.
9. A `DeprecationWarning` in a test fails `make test`.
10. The Docker image builds, imports the package, and runs as a non-root UID.

## Test plan

Tests were written after the implementation in this first pass — a deviation recorded in the build
notes. From F2 onwards the order is test first. Canaries (below) are the evidence that each guard
rail actually fails when broken.

## Risks

| Risk | Mitigation |
|---|---|
| Guard rails that pass because they checked nothing | Every scanner fails closed: gitleaks checks the commit count, the licence gate checks the package count |
| Pinned SHAs going stale | Dependabot updates the actions weekly |
| Local and CI definitions drifting | CI calls the same `make` targets |

## Effort

F0: 3 dev-days. F1: 1 dev-day.

## Open questions

- Which organisation owns the copyright in `LICENSE`? Currently a person, pending a company.

## Build notes (added during build)

- **Deviation 1:** implementation preceded the tests. The budget and LLM code was written first,
  then covered. Recorded rather than hidden; from F2 the order is test first.
- **Deviation 2:** the budget and LLM modules were described as already built in the design
  document but did not exist on disk; they were implemented here to that specification.
- **Deviation 3:** this plan was written after the code, not before it. The plan is therefore a
  record of decisions taken, not a signed-off design.

### Canaries (§10.4)

Every guard rail was deliberately broken, and the command re-run. Results:

| # | Break | Command | Result |
|---|---|---|---|
| C1 | Committed a fake GitHub token | `make secrets` | Caught: 1 leak. **Finding:** the first attempt used `AKIAIOSFODNN7EXAMPLE`, which gitleaks allowlists as a documentation example, so it passed. Recorded because "the scanner ran" is not the same as "the scanner would catch a real key". |
| C2 | Secret scan in a repository with no commits | `scripts/secret_scan.sh` | Refused to pass: "no commits in history". |
| C3 | `from firebrief.llm import Router` in `firebrief.budget` | `make boundaries` | 1 contract broken. |
| C4 | Installed a package declaring `GPL-3.0-only` | `make licenses` | Rejected, naming the package. |
| C5 | Added a dependency without updating the lock | `uv sync --locked` | Refused: "the lockfile needs to be updated". |
| C6 | A test emitting a `DeprecationWarning` | `make test` | Suite failed, because warnings are errors. |
| C7 | Deprecated API usage | `make types` | Caught during the build itself: `@contextmanager` with an `Iterator` return is deprecated, flagged as an error by `reportDeprecated`, and fixed to `Generator`. |
| C8 | Non-root container | `make docker-smoke` | Image built, `firebrief 0.1.0` printed, `uid=10001(app)`. |

Two operational notes from running them:

- The Dockerfile used BuildKit cache mounts, which this environment's credential helper could not
  resolve. The mounts were removed; layer ordering still caches the dependency install, and the
  image now builds with either builder.
- `make check` deliberately excludes the secret scan: it needs full git history and, in this
  environment, Docker. CI runs `make secrets` as its own step, and the PR checklist requires it.

