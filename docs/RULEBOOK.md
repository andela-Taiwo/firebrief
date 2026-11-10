# Rulebook

Rules earned from actual failures in this repository. Each one names the incident that
produced it, so it is a record rather than advice. The engineering playbook says what a
project must do; this says how *this* project has repeatedly got it wrong.

Read this before writing a test, running a canary, or claiming a change is done.

---

## R1. A test that passes when the behaviour is removed is not a test

**Incident.** Removing the vector side of retrieval broke no test: the paraphrase query
`closing flat entrance door` was being satisfied by full-text search, because Postgres
splits the hyphen in `self-closing`. The suite was green for the wrong reason.

**Rule.** Every guard gets a canary: remove the behaviour, confirm a specific test fails,
restore. If the canary does not fail, that is a finding, not a formality.

**Check.** `scripts/canary.py`. A canary that cannot fail is worse than none, because it
reports safety it never tested.

## R2. A patch that does not apply is a change that did not happen

**Incident.** Two canary patches silently failed to match after `ruff format` reflowed the
file. The canary ran against unmodified code, passed, and was reported as caught. It
happened twice in one session.

**Rule.** Every string replacement asserts its anchor exists first. No exceptions, however
small the patch.

**Check.** `scripts/canary.py` raises on a missing anchor and restores the file in a
`finally` block.

## R3. Verify from a clean clone, never a dirty tree

**Incident.** `tests/__init__.py` existed locally but was never committed. Ruff saw a
package, CI did not, and `I001` failed only on GitHub while `make check` was green locally.

**Rule.** Before pushing: `make check-clean`, which clones the repository to a temporary
directory and runs the suite there.

**Check.** `scripts/check_clean_clone.sh`.

## R4. Pin exact values, not "something happened"

**Incident.** A parse test asserted `DEAD_ENDS in claims[1].text or claims[1].quotes` —
always true, testing nothing.

**Rule.** Assert the exact value, count or status. If the assertion would pass with the
implementation deleted, rewrite it.

## R5. Say what a test is worth

**Incident.** "Recall@3 = 1.00" was reported as a quality result. It was six questions over
three sections with a bag-of-words embedder.

**Rule.** A test that a trivial implementation would pass is a smoke test. Name it that in
the docstring, and put the real quality gate in the evaluation harness.

## R6. Do not edit a migration that has been applied anywhere

**Incident.** Editing an unmerged migration was fine, but it left the local schema ahead of
the file and required rebuilding the database from an empty schema twice.

**Rule.** Edit a migration only before it is merged. After that, add a new one. If you do
edit an unmerged migration, record the schema reset in the plan.

## R7. Never claim a change without the command that shows it

**Incident.** I reported that the update/delete isolation tests were parametrised over every
tenant table. They were not: the patch had not matched, and I never ran the command that
would have contradicted me. The suite count gave it away afterwards.

**Rule.** The claim and its command go in the same message. "Should be" is not evidence;
"ran" is.

## R8. Commit only what the message describes

**Incident.** `git add -A` staged an in-progress feature, and the "docs" commit swallowed
`src/` and `tests/`. The history had to be rebuilt.

**Rule.** Stage explicit paths per commit and check `git log --stat` before pushing.

## R9. Do not rewrite published history, and never backdate

**Incident.** A request to backdate commits six months. Refused.

**Rule.** Real dates, real order. Rewriting before the first push is a correction; after it
is a fabrication.

## R10. A scanner that scanned nothing must fail

**Incident.** gitleaks reports "no leaks found" when it can read no commits; a licence gate
returns success when it scans zero packages.

**Rule.** Every scanner checks that it had something to check, and fails closed otherwise.

## R11. State the limits of a guard in the same breath as the guard

**Incident.** "Append-only" is enforced by triggers, which the table owner can disable. The
claim was true for the runtime role and false for the owner.

**Rule.** Say which roles the guarantee holds for. Put the rest in an ADR.

## R12. Branch from the branch you will merge into

**Incident.** The rulebook branch was cut from the citation-verifier feature branch, so its
pull request carried that whole unreviewed feature as well as the rulebook.

**Rule.** Cut a branch from `main` (or from whatever it will merge into), then check
`git log --oneline main..HEAD` and `git diff --stat main...HEAD` before opening the pull
request. If the branch is not what the title says, it is not ready.

---

## The two that cost the most

If you only remember two: **R1** (prove the test can fail) and **R3** (prove it on a clean
clone). Every other rule here has bitten once; those two have bitten repeatedly.
