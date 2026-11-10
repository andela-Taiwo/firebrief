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

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | Cross-tenant foreign keys were back | Both auth tables now use `(tenant_id, user_id) → users(tenant_id, id)`. A test inserts a tenant-A session for a tenant-B user and the database refuses it |
| **Must** | The isolation suite had shrunk around the new tables | The fixture seeds one link and one session per tenant; the visibility, update and insert tests cover all four tenant tables again. Delete stays covered by the grant test |
| **Must** | Email matching was case-sensitive | Addresses are normalised on write and matched with `lower(email)`, enforced by a unique index on `(tenant_id, lower(email))`. A mixed-case login works; a second user differing only by case is refused |
| **Must** | Email scanners would consume links on GET | Recorded in the contract below: `login_with_magic_link` must only be called from a POST, after a confirmation page |
| Should | The app role could update any column | Column grants: `update (consumed_at)` and `update (revoked_at)` only. Extending an expiry is refused, tested |
| Should | Old links stayed valid | Consuming one link invalidates the user's other open links, and at most three are kept open |
| Should | Bad tokens were handled inconsistently | `resolve_session` catches only `InvalidToken`; revoking a malformed token is a no-op rather than a 500 |
| Should | `NullEmailSender` failed silently | It logs a warning on every swallowed send |
| Minor | Vacuous assertions | Replaced with an assertion that the stored hash does not contain the secret |
| Minor | Inline `asyncio` import | Moved to the top |
| Minor | Non-member message leaked more | The generic message is used for both cases |

### Contract for the API layer

`login_with_magic_link` consumes the link. It must be called from a **POST** that follows a
confirmation page, never from the GET that an email scanner will fetch. Everything else
about token handling — clearing the URL, the `HttpOnly` cookie, CSRF on cookie-authenticated
POSTs, keeping tokens out of logs — is `api-hardening`'s job and is recorded there.

### Carried forward

- **Email-first login** needs one narrow privileged lookup (email → tenant ids), for example
  a `security definer` function returning only tenant ids for an exact normalised address.
  It is the one place auth would have to look across tenants, so it deserves its own review.
- **Timing** differs between a known and unknown address. Queue the send so the endpoint
  takes one path, and rate-limit per address and per IP.
- **Retention**: expired links and sessions accumulate and the app role cannot delete them.
  A privileged purge job belongs with the audit log's purge path.
- **Revoke all sessions** for a user, needed by "log out everywhere" and offboarding.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C70 | Composite key replaced with a plain user key | cross-tenant row test |
| C71 | Lookup case-sensitive | mixed-case login |
| C72 | Other links not invalidated | stale-link test |
| C73 | Table-wide update grant | expiry-extension test |

## Re-review 2 responses

| Severity | Finding | Response |
|---|---|---|
| Before merge | The POST-only contract must be written down | It is in the "Contract for the API layer" section above **and** in `login_with_magic_link`'s docstring, where a caller will actually see it |
| Before merge | The constraint tests could pass on a different constraint | Both now assert the constraint name: `fk_auth_sessions_tenant_user` and `uq_users_tenant_email_lower` |
| Before merge | Delete denial was tested for sessions only | Parametrised over `auth_magic_links` and `auth_sessions` |
| Should | `resolve_session` still caught every exception | Narrowed to `InvalidToken`; a database failure now surfaces instead of reading as "logged out". Two earlier patches had silently missed this line, which is why it survived two reviews |
| Should | The link was sent to the typed address | Sent to the stored address, so whitespace and case in the input cannot produce a different recipient |
| Should | "Consumed" conflates used and superseded | **Decided, not yet built:** `ended_reason` (`used` \| `superseded`) lands in the audit PR's migration, because that is where the distinction is consumed. Until then the column is absent and the audit log cannot tell them apart — recorded rather than implied |
| Should | Two overlapping email constraints | `uq_users_tenant_email` is superseded by the `lower(email)` index and will be dropped in a later migration; **onboarding must store normalised addresses**, since nothing enforces that yet |
| Should | One UPDATE per stale link | A single `update ... where id in (...)` |
