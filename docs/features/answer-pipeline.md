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
