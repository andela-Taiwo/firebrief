# api-hardening: the surface a browser talks to

**Status:** In progress · **Branch:** `feat/api`
**Depends on:** `auth`, `guardrails`, `answer-pipeline` · **Unblocks:** `web-ui`

## Goal

Four routes, a session cookie, one request id, and no path where a question reaches a log
line. Everything the browser needs to log in and ask a question, and nothing else.

## Scope

**In**
- `POST /v1/auth/magic-link`, `POST /v1/auth/verify`, `POST /v1/auth/logout`,
  `GET /v1/auth/me`.
- `POST /v1/answers` — retrieval, the pipeline and the verifier behind a session.
- `GET /health`.
- A request id that appears on the response, in the access log and in the answer result.
- Cookie handling: `HttpOnly`, `SameSite=Lax`, `Secure` by configuration.

**Out (and where it goes)**
- Rate limiting: `rate-limiter` (F12). Login is the first endpoint that needs it.
- The UI: `web-ui` (F19).
- OpenAPI hardening beyond FastAPI's defaults: not needed for one client.

## Decisions & trade-offs

### D1. The cookie is the session, and the token never goes in a URL
The magic link carries a token in a URL because that is how email works; the session does
not. `HttpOnly` means a script cannot read it, `SameSite=Lax` means a cross-site form post
does not carry it, and a state-changing request with an `Origin` that is not allowed is
refused — because `SameSite` alone does not cover every browser and every case.

### D2. Log only the shape of the request
The access line carries method, path, status, duration and request id. It never carries a
body. A question containing an email address is not in the log, which a test asserts.

### D3. One request id
The same id is on the response header, in the access line and on `AnswerResult`, so the
answer, its cost and its audit record can be joined without guessing.

### D4. The endpoint returns the refusal, not an error status
A refusal is a real answer: `200` with a reason, a message and the evidence considered.
Only authentication and malformed requests are `4xx`.

## Acceptance criteria

1. `/health` is public.
2. Asking for a link returns `202` whether or not the address exists, and sends at most one.
3. Verifying sets an `HttpOnly`, `SameSite=Lax` cookie; `/me` returns tenant, user and role.
4. `/v1/answers` without a session is `401`.
5. A verified answer returns the answer, its sources and a request id matching the header.
6. A question containing an email address never appears in the log.
7. A cross-origin POST is refused.
8. Logging out ends the session.

## Test plan

Routes are tested through the ASGI app against real PostgreSQL as the runtime role, with a
recording email sender and the fake provider. Canaries: remove the origin check; log the
body; drop `HttpOnly`.

## Risks

| Risk | Mitigation |
|---|---|
| A framework detail leaking the body into logs | FastAPI does not log bodies, and a test asserts the question is absent |
| Cookie theft via XSS | `HttpOnly`, plus the UI never renders untrusted HTML |
| No rate limit yet | Recorded; login is first in line for it |

## Effort

3 dev-days, one PR.

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | A deployed app would not judge support | `judge` is a required argument with no default, and a construction test asserts `create_app` refuses to be called without one |
| **Must** | Budgets were not enforced | `budget` is required and the route passes it with a scope built from the session; a user over their limit gets `budget_exhausted` over HTTP |
| **Must** | The origin check blocked the app's own UI and allowed no-Origin posts | The request's own origin is always allowed; a body must be JSON, because a browser cannot send that cross-site without a preflight; with no Origin the Referer must match |
| **Must** | The client chose the request id | Always generated on the server. The client's value is validated (`[A-Za-z0-9-]{1,64}`) and logged as `client_request_id`, never used as the id |
| Should | The role check did not run at startup | A lifespan handler runs it, so a deployment that cannot keep tenants apart fails to start. `/ready` re-checks the database and the role; `/health` only says the process is alive |
| Should | No security headers | `Cache-Control: no-store` on auth and answer responses, `X-Content-Type-Options: nosniff`, and the `__Host-` cookie prefix when `Secure` is on |
| Should | Sources were not tied to the answer | Each source carries `cited` and its verified quotes with character offsets |
| Should | `database_url` was a credential-bearing default | Removed; the engine is injected |
| Should | Uvicorn's access log records the full URL | Recorded for deployment: run with `--no-access-log`, because this middleware already logs the path without a query string |
| Test | The enumeration test depended on run order | `seeded` added |
| Test | The log test watched one logger | Now `caplog.set_level(DEBUG)` across all loggers |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C81 | The judge falls back to an accept-all default | judge-required test |
| C82 | The budget is not passed to the pipeline | budget-exhaustion test |
| C83 | Same-origin POST refused under default settings | same-origin test |
| C84 | The client's request id is used as-is | client-request-id test |

### Next

Rate limiting, per the review: magic links per address and per IP, answers per user. It is
the last documented hole before a public demo, and building it before the UI means the UI
can show "limit reached" from the start.
