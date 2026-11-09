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
