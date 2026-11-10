# answer-pipeline: retrieval, a model, and a verifier that can say no

**Status:** In progress · **Branch:** `feat/answer-pipeline`
**Depends on:** `hybrid-retrieval`, `citation-verifier` · **Unblocks:** `refusal-and-evidence`, `eval-harness`

## Goal

Turn a question into either a cited answer that survives verification, or an explicit
refusal that names why. The model is one step in the middle, not the product.

## Scope

**In**
- A prompt that states the contract: quote at least six consecutive words per citation,
  one quote per marker, no ellipses, no quotation marks for emphasis, and
  `INSUFFICIENT_EVIDENCE` when the sources do not answer.
- A pipeline: retrieve, reserve budget, call the single gateway, settle, verify, answer or
  refuse.
- Refusal reasons as data: no sources, insufficient evidence, unverified, model
  unavailable, budget exhausted.
- The verifier sits between the model and the caller. It is not optional.

**Out (and where it goes)**
- Streaming: needs the frontend and is a separate concern.
- The real judge model: wired at the gateway in F8b, with its own evaluation.
- Answer quality measurement: `eval-harness` (F10).

## Decisions & trade-offs

### D1. Refuse rather than degrade
Every path that cannot produce verified evidence returns a refusal with a reason, never a
best-effort answer. The reason is shown to the user and written to the audit log.

### D2. Budget before the call, not after
The reservation happens before the model is called, so a request that would exceed a
limit never spends money. If the call fails, the reservation is released.

### D3. The prompt is part of the contract
The verifier requires verbatim quotes, so the prompt must demand them and say what
happens otherwise. Prompt and verifier are tested together: a prompt change that breaks
the contract shows up as a failing test, not as a mysterious refusal rate.

## Acceptance criteria

1. A model answer whose quotes exist in the cited sources is returned, with its sources.
2. A model answer with a fabricated quote is refused as `unverified`, and the verification
   is returned so the refusal can be explained.
3. `INSUFFICIENT_EVIDENCE` from the model is refused as `insufficient_evidence`.
4. No retrieved sources means a refusal, and the model is not called.
5. A provider failure is a refusal as `model_unavailable`, not an exception.
6. A budget rejection is a refusal as `budget_exhausted`, and the model is not called.
7. A successful answer settles the reservation at the provider's exact usage.
8. The prompt numbers the sources and includes the question; the system prompt states the
   quoting contract.

## Test plan

The pipeline takes already-retrieved sources for its unit tests, so no database and no
network are needed. A model is a scripted `FakeProvider`. One integration test wires
retrieval in. Canaries: skip verification; call the model before the budget check; ignore
`INSUFFICIENT_EVIDENCE`.

## Risks

| Risk | Mitigation |
|---|---|
| A prompt that asks for quotes and gets none, refusing everything | The eval harness measures the refusal rate; the prompt is versioned |
| Model answers cite a plausible but wrong source | The verifier checks the quote in the source the marker names |
| Budget refusal reads like an error | Refusal reasons are distinct and user-facing |

## Effort

3 dev-days, one PR.

## Build notes

- **This branch is stacked on `feat/citation-verifier`**, because the verifier is not merged
  yet. Its pull request must be based on that branch, not on `main`. Merging order matters:
  verifier first, then this.
- **Refusals are data**, not exceptions: `no_sources`, `insufficient_evidence`,
  `unverified`, `model_unavailable`, `budget_exhausted`. The verification object is carried
  on the refusal so the reason can be explained without re-running anything.
- **Budget is reserved before the call and released on failure.** A request that cannot
  afford its worst case never reaches the model.
- **The model is a `Provider`, not a `Router`.** The router is one, so production passes a
  router and tests pass a scripted fake.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C44 | Verification skipped | fabricated-quote test shows the answer |
| C45 | Budget checked after the call | budget test calls the model |
| C46 | `INSUFFICIENT_EVIDENCE` ignored | decline test answers instead of refusing |

## Refusals as an outcome, not an error

A refusal now carries what a person needs to act on it: a reason code, a plain-language
message, the evidence that was considered, and — when verification failed — the specific
checks that failed. `for_audit()` produces the record to store: reason, message, details
and where the evidence came from, without the passage text.

The five messages are written for a reader, not a log:

| Reason | What the reader is told |
|---|---|
| `no_sources` | Nothing covers that question, and it will not guess |
| `insufficient_evidence` | Guidance exists on the topic but not enough to answer |
| `unverified` | Relevant guidance was found but the answer could not be checked against it |
| `model_unavailable` | Service down, nothing charged |
| `budget_exhausted` | The usage limit would be exceeded |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C47 | Verification details dropped from the refusal | failing-checks test |
| C48 | Audit payload includes the passage text | audit test asserts `text` is absent |

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | Reservation IDs collided for identical questions | A UUID per request, returned on `AnswerResult.request_id`. Two identical questions produce two reservations; tested, and the canary sets it back to `question[:64]` |
| **Must** | Only an exact `INSUFFICIENT_EVIDENCE` was recognised | `is_insufficient` reads the first line, ignores case and surrounding quotes or punctuation, so `"INSUFFICIENT_EVIDENCE."` and an explanation on the next line both refuse correctly. Parametrised over five variants |
| **Must** | Truncated answers were reported as unverified | `LLMResponse` carries the provider's finish reason; `max_tokens`/`length` refuse as `TRUNCATED`, with its own message |
| **Must** | Tests missing | Added, and the assertions tightened below |
| Should | Usage dropped on the unverified path | Every refusal after a call carries `usage`; tested |
| Should | Default model hard-coded | **Deferred.** The model is a parameter with a documented default. Choosing it from configuration and checking at start-up that every configured model has a price belongs with deployment (F21), not here |
| Should | Budget exceptions escaped | `reserve` failures refuse with `BUDGET_EXHAUSTED`; settle and release failures are logged and swallowed. Recorded in ADR 0007 |
| Should | Budget refusal message was vague | The rejection's `reset_at` is now in `details` |
| Should | Details compared strings | Details use the `Status` enum and include the marker and the quote, pinned by test |
| Should | Prompt did not delimit untrusted text | Sources are `<source n="…" edition="…">` and the question is `<question>`, with an instruction to treat them as data |
| Should | Tidy-ups | Single `strip()`, provider exceptions logged by type |
| Look-ahead | Judge and query-embedding costs are unbudgeted | Recorded below as an explicit follow-up, not silently dropped |

### Tests strengthened

Exact settlement (`price.cost(10, 5)`), `spent == 0` after a failed call, an untouched ledger
after a budget rejection, the exact detail string, a genuine quote rejected by the judge,
the judge not called on no-sources or decline, prompt ordering with two sources, and the
integration tests now run as the **runtime role** rather than the owner.

### Recorded for the next PRs

- **Judge cost.** Each answer makes one generation call plus one call per quote; the
  judge's worst case must be reserved alongside generation, or budgets understate spend.
- **Query embedding cost.** Still unbudgeted for the same reason: retrieval has no tenant.
- **Partial answers.** Withholding everything for one bad claim is safe but may withhold
  too often; compare one budget-aware regeneration against showing only verified claims.
  Track withhold rate as an evaluation metric.
- **Streaming.** Nothing is shown until verified, so stream stage progress, not tokens.
- **Audit context.** Pass a request context (request ID, tenant, scope, per-stage timings)
  through `answer_question` before the API is built.
- **Context budget.** `limit=6` chunks is a count, not a token budget; cap total source
  tokens in `build_prompt` before long documents arrive.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C49 | Request ID falls back to the question text | two-questions test sees the same ID |
| C50 | Decline detection requires an exact match | variants test refuses as unverified |
| C51 | Truncation not checked | truncated test reports unverified |


## Re-review 2 responses

| Severity | Finding | Response |
|---|---|---|
| Should | A ledger outage was reported as "limit exceeded" | `BUDGET_UNAVAILABLE` with its own message, detail naming the exception type, and a test whose budget raises. ADR 0007 records it |
| Should | Unrelated questions reached the model and were called "relevant guidance" | `answer_question` takes `min_similarity` and passes it to retrieval, so a floor refuses as `no_sources` before any call. The default stays unset — a floor is per embedding model and must be calibrated, not guessed (ADR 0006 addendum). The existing behaviour is now a test named for what it documents, not an endorsement |
| Should | The question could forge source markup | The question, title, heading, edition and text are HTML-escaped before they enter the prompt; tested with a hostile question |
| Minor | Two identical questions were only tested sequentially | An `asyncio.gather` version asserts two reservations and double the spend |
| Minor | Truncation test checked only the reason | It now also asserts usage is recorded and the judge was not called |

### Carried into the next PRs

- **Settle and release failures leak capacity.** `_safe` keeps a bookkeeping failure from
  crashing an answer, but a failed release holds the reservation for good. The Postgres
  ledger needs reservation expiry and a sweeper, with a test whose settle raises.
- **Pricing after failover.** Settlement prices the reserved model; if the router fails
  over, the charge should follow `response.model`, and the reservation should cover the
  most expensive route.
- **Providers' own refusals.** Anthropic's `refusal` and OpenAI's `content_filter` need a
  distinct reason rather than falling through to verification.
- **Audit record.** `AnswerResult` carries a request ID; the audit PR needs tenant,
  per-stage timings, retrieval scores, the judge record and cost.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C52 | Outage reported as an exhausted limit | outage test |
| C53 | `min_similarity` not passed to retrieval | floor test calls the model |
| C54 | Prompt escaping removed | hostile-question test |
