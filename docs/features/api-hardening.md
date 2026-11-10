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
