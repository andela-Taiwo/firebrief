# auth: a magic link, a session, a tenant

**Status:** In progress · **Branch:** `feat/auth`
**Depends on:** `tenant-isolation` · **Unblocks:** `audit-log`, `api-hardening`

## Goal

A person proves who they are with an emailed link, gets a session, and every query they
make runs inside their tenant. No passwords, no long-lived tokens in the browser, and
nothing secret stored in a readable form.

## Scope

**In**
- Magic-link request and consumption, with a single-use, expiring, hashed token.
- Sessions: expiring, revocable, hashed at rest, carrying tenant and role.
- Tokens carry the tenant id in the clear and the secret in the random part, so a
  verification can open the right tenant session **before** querying. Row-level security
  stays intact; there is no cross-tenant lookup.
- An `EmailSender` port with a recording sender for tests.

**Out (and where it goes)**
- The HTTP endpoints: `api-hardening` (F18). This PR is the domain layer, so the security
  properties are tested without a framework in the way.
- OIDC/SSO: the adapter lands behind the same interface later.
- Rate limiting login attempts: `rate-limiter` (F12).

## Decisions & trade-offs

### D1. The tenant id is in the token, the secret is not
Verification needs a tenant before it can query, and looking a token up across tenants
would need a privileged connection. Putting the tenant id in the token keeps every query
inside a tenant session. The tenant id is not a secret; the 32-byte random part is.

### D2. Only hashes are stored
The database stores SHA-256 of the token, never the token. A database read cannot mint a
session. The same is true of the magic link.

### D3. Unknown emails are not revealed
Requesting a link for an address that is not in the tenant returns the same shape and sends
nothing. The response must not become a user-enumeration oracle.

### D4. Expiry and single use are enforced in the query, not the caller
Consumption marks `consumed_at` in the same transaction that checks it, so two concurrent
consumptions cannot both succeed.

## Acceptance criteria

1. Requesting a link stores only a hash and sends a token to the address.
2. An unknown address stores nothing and sends nothing.
3. Consuming a valid link returns a session and a context with tenant, user and role.
4. Consuming twice fails, and the second attempt does not create a session.
5. An expired link fails.
6. A revoked or expired session resolves to nothing.
7. The plaintext token never appears in the database.
8. Auth tables are tenant-isolated like every other tenant table.

## Test plan

Token format and hashing are pure and tested without a database. The service is tested
against real PostgreSQL, **as the runtime role**, so the grants and policies are exercised.

Canaries: store the token instead of its hash; drop the consumed check; drop the expiry
check.

## Risks

| Risk | Mitigation |
|---|---|
| Email delivery is a dependency in tests | A recording sender; the real sender is wired at deployment |
| A leaked database grants sessions | Only hashes are stored |
| Enumeration by timing | Same code path for unknown addresses; timing is not equalised yet, and that is recorded |

## Effort

3 dev-days, one PR.

## Build notes

- **One statement claims a link.** The first version checked expiry and use, then updated —
  two guards for one fact. A canary removing the update's conditions changed nothing,
  because the pre-check still caught it. The check and the claim are now the same
  `UPDATE ... WHERE consumed_at IS NULL AND expires_at > now RETURNING rowcount`, with a
  concurrent test: two logins with one link produce exactly one session.
- **Tenant id travels in the token** so a login can open the right tenant session before
  any query. Row-level security is never bypassed to look a token up.
- **The auth tables are delete-denied at the grant level.** Sessions are revoked, not
  removed; a test asserts the runtime role cannot delete them.
- **Timing is not equalised** between an unknown address and a known one. Recorded rather
  than fixed: it is a small oracle and the rate limiter is the next control.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C67 | The token is stored in clear instead of its hash | hash-in-database test |
| C68 | The single-use condition is dropped from the claim | double-use test |
| C69 | The expiry condition is dropped from the claim | expired-link test |
