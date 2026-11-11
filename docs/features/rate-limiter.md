# rate-limiter: bound the two things worth abusing

**Status:** In progress · **Branch:** `feat/rate-limiter`
**Depends on:** `api-hardening` · **Unblocks:** a public demo

## Goal

Magic links cannot be used to bomb an address or a host, and answers cannot be run without
limit by one account. Three limits, checked before the expensive thing happens.

## Limits

| Scope | Key | Default | Window |
|---|---|---|---|
| Magic links per address | `rl:link:email:<sha256(normalised email)>` | 5 | 15 min |
| Magic links per IP | `rl:link:ip:<sha256(ip)>` | 20 | 15 min |
| Answers per user | `rl:answer:user:<sha256(tenant:user)>` | 60 | 1 h |

## Decisions & trade-offs

### D1. Hashed keys
The limiter store should not become a directory of every email address and IP that tried to
log in. Keys are SHA-256 of the normalised value; the store cannot be reversed into a
mailing list.

### D2. Fail closed
If Redis is unreachable, the request is refused with `503` rather than allowed. This matches
ADR 0007: a control that silently stops applying during an outage is not a control, and the
outage is exactly when abuse would go unnoticed.

### D3. The window is approximate
The Redis implementation is a sorted set read then written in separate commands, so two
concurrent requests can both be allowed at the boundary. For abuse protection that overshoot
is acceptable; making it exact needs a Lua script, which is not worth the complexity until
overshoot is shown to matter.

### D4. The limiter is injected
`create_app` requires a `Limiter`, like the judge and the budget. Tests use the in-memory
implementation; deployment uses Redis. Neither is a default.

## Acceptance criteria

1. The sixth link request for one address in the window is `429` with `Retry-After`.
2. Requests from one IP are limited across different addresses.
3. The 61st answer in an hour for one user is `429`.
4. Keys contain no address, IP or user id.
5. A limiter that raises produces `503`, not a pass.
6. The window slides: an event older than the window no longer counts.

## Test plan

The in-memory limiter is tested with a fake clock for window behaviour. The Redis limiter is
tested against `fakeredis`. The API tests assert `429`, `Retry-After`, and `503` on outage.

Canaries: skip the magic-link check; store keys in clear; fail open on an outage.

## Risks

| Risk | Mitigation |
|---|---|
| A shared IP (office, carrier NAT) blocks innocent users | The per-IP limit is 4× the per-address limit, and both are configurable |
| A user past their limit has no path forward | `Retry-After` is sent so the UI can say when |
| Redis becomes a hard dependency of login | It already was for the budget's fast path; fail-closed is the recorded choice |

## Effort

2 dev-days, one PR.

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | The IP limit could be spoofed or shared by everyone | `X-Forwarded-For` is read from the right, by the configured number of trusted hops, so the leftmost (client-written) entries cannot choose a bucket. A platform header (`client_ip_header`, e.g. `fly-client-ip`) takes precedence. Production refuses to start with neither configured, and a test asserts it |
| **Must** | A refused IP still spent the victim's address quota | The IP is checked first, and the address is only counted once the IP is allowed. A test drives a blocked IP against one address and then shows a different IP still has the address quota intact |
| **Must** | The Redis overshoot was unbounded under parallel requests | One `MULTI` pipeline adds the candidate, prunes the window, counts and refreshes the TTL; a count over the limit removes the candidate and refuses. A test fires ten concurrent checks at a limit of two and asserts at most two are allowed |
| **Must** | Hashed keys could be reversed by guessing | `key_for` takes a server secret and uses HMAC-SHA256, so the store cannot be brute-forced. Rotating the secret resets the counters. Tested by changing the secret |
| Should | The Redis test could silently skip | `fakeredis` is pinned and `importorskip` is gone |
| Should | A docstring was orphaned in `Settings` | Moved back under `allowed_origins` |
| Should | `/v1/auth/verify` had no limit | A generous per-IP limit, 60 per window |
| Should | `remaining` was computed and never sent | `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset` on allowed responses |
| Minor | The Redis clock is the app's, so instances can skew | Recorded in the module docstring rather than hidden |
| Minor | The TTL was refreshed outside the pipeline | It is set inside the pipeline now |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C91 | The leftmost `X-Forwarded-For` entry is trusted | spoofed-header test |
| C92 | The address is counted before the IP is allowed | blocked-IP quota test |
| C93 | The Redis check is not exact | parallel-requests test |
| C94 | The key is a plain hash instead of an HMAC | secret-rotation test |

## Re-review 2 responses

| Severity | Finding | Response |
|---|---|---|
| Should | The production checks were skipped whenever `environment` was not exactly `"development"` | It is a `Literal["development", "test", "production"]` and the **default is `production`**, so a deployment that forgets the variable gets the checks rather than a pass. A typo now fails validation; a test asserts it |
| Should | `client_ip_header` is trusted on any request | Documented in the setting: it is only trustworthy when the app cannot be reached except through that platform. The deployment docs repeat it |
| Should | IPv6 users own a /64 and could rotate for free | Addresses are bucketed by `/64` prefix. A test sends two addresses in one /64 and expects the second to be refused, and one from a different /64 to pass |
| Minor | `RateLimit-Reset` is the whole window | Documented as an upper bound in the helper |
| Minor | Two limits overwrite each other's headers | The tighter one wins: headers only move when `remaining` is lower. The test puts the tighter limit first, so "last write wins" would fail it |
| Minor | Headers were lost when a route returned its own `JSONResponse` | Copied onto the returned response, so a budget `429`/`503` still carries them |
| Minor | Refusals carried no rate-limit headers | Added, with `Retry-After`; the limiter's `503` sends `Retry-After: 5` |
| Minor | `/verify` reused the link window | `verify_window_seconds` is its own setting |
| Minor | Secrets were not required to be strong | Production requires at least 32 characters, tested |
| Minor | A failed rollback inflates the count until the window passes | Noted in the module docstring: it fails safe and is short-lived |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C95 | `environment` becomes a free string | unknown-environment test |
| C96 | IPv6 counted per address | /64 test |
| C97 | Headers overwritten by the later limit | tighter-limit test |
