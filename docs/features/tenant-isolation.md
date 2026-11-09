# tenant-isolation: every tenant-owned row is invisible to every other tenant

**Status:** Awaiting sign-off · **Branch:** `feat/tenant-isolation` (not created)
**Depends on:** `repo-foundation` · **Unblocks:** `corpus-ingestion`, `auth`, `audit-log`

No code has been written for this feature. This plan exists so that sign-off can happen before
the first line of it, which is the order the playbook requires.

## Goal

A tenant's data is unreachable from another tenant's request, enforced by PostgreSQL row-level
security, failing closed. A developer who forgets a `WHERE` clause cannot leak data, because the
database will not return the rows.

## Scope

**In**
- `tenants`, `users`, `memberships` (role: owner | inspector | viewer).
- RLS on every tenant-owned table: `ENABLE` + `FORCE`, standard policy, `USING` and `WITH CHECK`.
- Tenant applied per transaction with `set_config('app.tenant_id', $1, true)`.
- A session factory that cannot produce a session without a named tenant.
- Start-up check refusing a role that is superuser, `BYPASSRLS`, or a member of such a role.
- The invariant test: every table is either policy-isolated by the standard expression, or on a
  reviewed list of global tables.
- Migration harness against real PostgreSQL, refusing any database not named `*_test`.

**Out (and where it goes)**
- Login, magic links, OIDC: `auth` (F14).
- Permission checks beyond the three roles: `rbac` (F17).
- Audit writing: `audit-log` (F15).
- Corpus tables: `corpus-ingestion` (F3). The guidance corpus is global, not tenant-owned, and
  will be on the reviewed global list.

## Decisions & trade-offs

### D1. Row-level security, not application-level filtering
| Option | For | Against |
|---|---|---|
| **RLS with FORCE (recommended)** | One forgotten filter cannot leak; the policy is testable as an invariant | Needs a per-transaction setting; slightly harder to debug |
| Repository-level `WHERE tenant_id = ?` | Simple, no database features | Every new query is a chance to leak; no invariant can prove safety |

The failure mode is silent cross-tenant disclosure. That is the one failure this product cannot
survive, so it belongs in the database.

### D2. Tenant set per transaction, never per session
`set_config(..., true)` is transaction-local, so a pooled connection cannot carry one tenant's
setting into the next request. Session-level `SET` is rejected: it survives the pool's reuse.

### D3. One database, one app role, `tenant_id` on every row
Not a database or schema per tenant. Physical isolation would multiply migrations and connections
for no security gain here, and the postgres role is already least-privilege.

### D4. The `tenants` table itself
A tenant may select and update its own row. There is **no delete policy**: deletion cascades to all
of that tenant's data, so offboarding is an operator action, audited elsewhere.

### D5. Background jobs get a tenant explicitly
A job that touches tenant data must be handed a tenant id at enqueue time and set it in its own
transaction. A job with no tenant sees nothing and writes nothing — same fail-closed rule.

## Acceptance criteria

1. With no tenant set, `SELECT` on each tenant table returns zero rows and `INSERT` raises.
2. With tenant A set, no row belonging to tenant B is visible, for every tenant table.
3. The application refuses to start when its database role is superuser, has `BYPASSRLS`, or is a
   member of a role that has it. The process exits non-zero with a message naming the reason.
4. `SET ROLE` to a privileged role does not bypass the policy.
5. The invariant test enumerates every table in `public` and fails unless it is policy-isolated or
   on the reviewed global list.
6. The invariant test checks the **policy expression**, not merely that a policy exists — a policy
   of `USING (true)` fails.
7. `Alembic upgrade → downgrade → upgrade` passes against real PostgreSQL, and the drift check is
   clean.
8. The test harness refuses to run against a database not named `*_test`, checked both from the URL
   and from `SELECT current_database()`.

## Test plan

Tests written first. The first red run to capture: the invariant test against the freshly migrated
schema, failing because no policies exist yet, with the failure naming the tables.

Then, in order: no-tenant behaviour, cross-tenant reads, policy expression, startup role check,
`SET ROLE`, migration round-trip, and the `*_test` guard.

Canaries to run before the PR:
- Drop `FORCE ROW LEVEL SECURITY` from one table → invariant test must fail.
- Change a policy to `USING (true)` → expression test must fail.
- Connect as a superuser → the app must refuse to start.
- Point the harness at `firebrief_dev` → it must refuse, from both the URL and `current_database()`.

## Risks

| Risk | Mitigation |
|---|---|
| A pooled connection carries a tenant between requests | Transaction-local `set_config`, plus a test that reuses a connection |
| A new table is added without a policy | Invariant test over `pg_class`, run in CI, not a checklist |
| Migrations run as the owner, who bypasses RLS | `FORCE` applies policy to the owner; the migration role is still checked at start-up |
| Test harness resets a development database | Double guard: URL and `current_database()` |

## Effort

5 dev-days, one PR.

## Open questions

1. Does the review want the `memberships` role enum in the database (a Postgres enum) or in the
   application with a check constraint? Recommendation: check constraint, for easier evolution.
2. Is `firebrief_test` created by Compose init, or by the test harness? Recommendation: Compose,
   so the harness never creates databases.

## Build notes (added during build)

**Red run observed before implementation**, as planned:

```
tenant tables missing: ['memberships', 'tenants', 'users']
```

**Canaries (§10.4), each run against the live database and then restored:**

| # | Break | Caught by |
|---|---|---|
| C1 | `ALTER TABLE users NO FORCE ROW LEVEL SECURITY` | `test_rls_is_enabled_and_forced`: "FORCE ROW LEVEL SECURITY is not set" |
| C2 | Policy replaced with `USING (true) WITH CHECK (true)` | `test_policies_use_the_standard_expression`: "expression 'true' is not the standard tenant policy" |
| C3 | Runtime pointed at the superuser role | `test_a_superuser_is_refused`: "is a superuser" |
| C4 | Harness pointed at `firebrief_dev` | `owner_url`: "refusing to run against a non-test database URL" |

**Deviation 1:** the first version of the policy assertion required a `USING` clause on every
policy, which is wrong — an INSERT policy has only `WITH CHECK`. The test was corrected, not
weakened: it now inspects whichever expressions exist and still rejects `USING (true)`.

**Deviation 2:** `updated_at` is maintained by a `BEFORE UPDATE` trigger, so nothing in application
code assigns it.

**Finding for the next feature:** the runtime role's table privileges are granted by the test
harness, not by a migration. Deployments will need an equivalent grant step; it belongs with
`deployment` (F21), not here.

## Review findings and responses

| Sev | Finding | Response |
|---|---|---|
| B1 | Safety check ran after the destructive seed; URL guard was a substring match | `make_url()` now parses the URL and requires `endswith("_test")`; every engine fixture asks the server `current_database()` before it is used, so nothing destructive runs first |
| B2 | Delete check missed `FOR ALL` | Now rejects `{"DELETE", "ALL"}`, plus a behavioural test: the runtime role deletes zero rows from `tenants` |
| H3 | Policy check was brittle (NULL `with_check`, fragment matching, `permissive`/`roles` unverified) | Compares against one canonical normalised expression; checks `with_check` only for INSERT/UPDATE/ALL; asserts `PERMISSIVE` and `roles = {public}` |
| H4 | Foreign keys bypass RLS; a membership could point at another tenant's user | Composite key `(tenant_id, user_id) → users(tenant_id, id)` in `0003_composite_fk`, with a negative and a positive test |
| H5 | No proof the runtime role cannot bypass RLS | Tests assert `rolsuper = false`, `rolbypassrls = false`, and that it owns no tables |
| H6 | Merging the tests alone turns `main` red | This branch now contains the implementation; merge it squashed, as one feature |
| M | Tenant context leak between transactions on one connection | Test with `pool_size=1`: two transactions, two tenants, no carry-over |
| M | Isolation tests not parametrised over every tenant table | Parametrised over `users` and `memberships` |
| M | Seeding relied on a superuser | Truncate is the only privileged statement; rows are written through the runtime role inside a tenant session, so the seed exercises the policies too |
| M | Partitions and views unhandled | Invariant covers `relkind in ('r','p')`; no views exist, and any added view must be on the reviewed list |
| M | PR template placeholders | Template trimmed to prompts, not angle-bracket placeholders |

## Re-review responses

| Sev | Finding | Response |
|---|---|---|
| **B** | Migrations ran before the server-side database check | `migrated` now asks `current_database()` **before** alembic runs; the URL check uses `make_url(...).database.endswith("_test")` |
| **H** | Grants lived in a test fixture, so production never got them | `0004_grants` grants per table: tenants get SELECT/INSERT/UPDATE (no DELETE), users and memberships get full DML, `alembic_version` gets nothing. It revokes first, so a role with wider historical grants cannot keep them |
| **H** | Tenant delete was filtered, not refused | With DELETE not granted, the runtime role gets a permission error. The test now asserts the error rather than a zero row count |
| **H** | Only the superuser case was covered for the role check | Real roles created in tests: a BYPASSRLS role and a role that owns a table. `assert_safe_database_role` now also refuses a role that owns tables, because it could drop or replace the policies |
| M | Update/delete/insert tests covered `users` only | Parametrised over every tenant table |
| M | The NullPool leak test could never fail | Removed; the `pool_size=1` test is the real one |
| M | Tenant creation was open to any session with an arbitrary UUID | `0005_privileged_tenants` drops the INSERT policy. Creating a tenant is an onboarding action; the seed creates tenants as the owner |
| M | Views were not reviewed | The invariant now covers `relkind ('r','p','v','m')` |
| M | `test_the_database_is_a_test_database` is redundant | Kept deliberately, as executable documentation of the rule |
| M | PR title and description still said "before implementing it" | Rewritten for the reply; the code branch is unchanged |

### Canaries added by this round

| # | Break | Caught by |
|---|---|---|
| C7 | `GRANT DELETE ON tenants TO firebrief_app` | delete test: "DID NOT RAISE" |
| C8 | `GRANT SELECT, UPDATE ON alembic_version` | privilege test naming the granted privileges |
| C10 | Migrating with `FIREBRIEF_APP_ROLE` set to a role that does not exist | migration aborts: "does not exist; create it before" |

**Weak test found while canarying C8:** the first version asserted that an `UPDATE` on
`alembic_version` raised. It would have passed even with `UPDATE` granted, because `UPDATE`
also needs `SELECT` on the referenced column, which was absent. The test now asks
`has_table_privilege` for each of SELECT/INSERT/UPDATE/DELETE, so it fails for the right reason.
