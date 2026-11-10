# Contributing

One feature at a time. The loop is not optional, including for "small" changes that touch
behaviour.

## The loop

1. **Roadmap.** Add or update the row in `docs/ROADMAP.md`.
2. **Plan.** Write `docs/features/<feature-name>.md` from the template. Goal, scope, decisions
   with trade-offs, acceptance criteria, test plan, risks.
3. **Sign-off.** The owner approves the plan. No code before sign-off.
4. **Build.** Branch `feat/<feature-name>`. **Test first:** write the failing test, watch it fail
   for the right reason, make it pass, refactor.
5. **Self-review.** `make check` and `make secrets`, then try to break your own work.
6. **Independent review.** A reviewer who did not write the code runs probes and reports findings.
7. **Pull request.** Use the template. Every claim needs a command behind it.
8. **Owner review.** Changes requested, or squash-merge. The builder never merges their own PR.

## Commands

```bash
make setup      # install from the lockfile
make check      # lint, format, types, boundaries, licences, tests
make secrets    # gitleaks over the full history
make help       # every target
```

## Rules of the road

- Descriptive feature names (`citation-verifier`, not `F8`), used for the plan file, branch and
  PR title.
- Conventional Commits: `feat:`, `fix:`, `chore:`, `ci:`, `docs:`, `refactor:`, `test:`.
- Never rewrite history to misrepresent when or how work was done.
- No new dependency without checking its licence — the gate will fail it otherwise.
- Boundaries: `firebrief.budget` and `firebrief.llm` must not import each other, and neither may
  import the API layer. CI enforces it.

## Before you claim something works

Two habits, both in `docs/RULEBOOK.md` because both have gone wrong here:

- Prove the test can fail: `scripts/canary.py` removes one behaviour and insists a
  specific test goes red.
- Prove it on a clean clone: `make check-clean` clones the repository and runs the suite
  there, so a missing file cannot hide behind a dirty working tree.

## Requirements for a merge

- `make check` green and the secret scan green.
- Canaries recorded: which guard rail you broke, and which test caught it.
- Plan updated with any deviation from what was signed off.
