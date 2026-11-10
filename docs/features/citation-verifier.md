# citation-verifier: an answer is withheld unless its evidence is real

**Status:** In progress · **Branch:** `feat/citation-verifier`
**Depends on:** `hybrid-retrieval` · **Unblocks:** `answer-pipeline`, `refusal-and-evidence`

## Goal

Given an answer written as claims with citation markers, decide whether it may be shown.
A claim is only verified if its quoted passage exists in the source it cites. Anything
else — an unknown marker, a passage that is not in the source, a claim with no citation —
withholds the whole answer.

The point is not to catch typos. It is that a fire safety answer which cites a paragraph
that does not exist is worse than no answer, and this is the code that stops it.

## Scope

**In**
- Parse an answer into claims, quoted passages and `[n]` markers.
- Resolve markers against the retrieved sources, 1-based.
- **Existence check (deterministic):** the quoted passage must appear in the cited chunk,
  after whitespace and case normalisation.
- **Support check (optional):** a `SupportJudge` interface, with a fake; the real judge
  model is wired in a later PR, and the interface exists so the pipeline can be built
  against it.
- A verdict: `verified` or `withheld`, with per-claim status for the UI and the audit log.

**Out (and where it goes)**
- Writing the answer: `answer-pipeline` (F7).
- The real judge model and its evaluation: `citation-verifier` part 2, with the eval harness.
- Rendering withheld answers: frontend.

## Decisions & trade-offs

### D1. Quotes are the unit of existence
A claim that paraphrases cannot be checked deterministically. Requiring the model to quote
the passage it relies on turns verification into a substring test that either passes or
fails, and makes the citation visible to the user.

| Option | For | Against |
|---|---|---|
| **Quoted passage must appear verbatim (chosen)** | Deterministic, cheap, no model in the loop | The prompt must ask for quotes, and a model that paraphrases gets withheld |
| Check the claim sentence against the source | No quoting needed | Almost never matches; would withhold everything |
| Ask a judge whether the claim is supported | Handles paraphrase | Non-deterministic, costly, and it is the thing being verified |

### D2. Withhold rather than degrade
One unverifiable claim withholds the answer rather than dropping the claim, because a
partially cited answer invites the reader to trust the rest.

### D3. The judge is a second gate, not the first
Existence runs first and is free. The judge only sees claims that already quote real text,
so a judge failure cannot manufacture a citation that does not exist.

## Acceptance criteria

1. A claim whose quote appears in the cited source is verified.
2. A claim whose quote is absent from the cited source withholds the answer, with status
   `missing_span`.
3. A marker with no matching source withholds with `unknown_marker`.
4. A claim with no marker withholds with `uncited`.
5. Whitespace, line breaks and letter case do not affect existence.
6. An empty answer is withheld.
7. When a judge is supplied and rejects a claim, the answer is withheld with
   `unsupported`; when it accepts, the answer is verified.
8. Every check names the chunk it resolved to, so the audit log can show the evidence.

## Test plan

Pure unit tests: no database, no network, no model. Sources are `Retrieved` objects built
directly. Canaries: make existence always true; drop the uncited check; make the judge
always accept.

## Risks

| Risk | Mitigation |
|---|---|
| The model paraphrases and every answer is withheld | The prompt demands quotes, and the evaluation harness measures the withhold rate |
| A judge that always says yes | The judge is a second gate only; existence cannot be waived |
| Quotes that exist but do not support the claim | This is the judge's job, and its accuracy is measured, not assumed |

## Effort

2 dev-days, one PR.

## Build notes

- **Sentence merging.** Models write `Claim. [1]` as often as `Claim [1]`. A segment with
  no words of its own — only markers and quotes — is attached to the claim before it, so
  the citation belongs to the sentence it follows. Without this, a correctly cited answer
  was withheld as uncited, which the tests caught.
- **One unverifiable claim withholds the whole answer**, deliberately. A partly cited
  answer invites the reader to trust the uncited part.
- **The judge is optional and second.** Existence runs first and is free; a judge can only
  reject a claim that already quotes real text, never create a citation.

## Canaries

| # | Break | Caught by |
|---|---|---|
| C35 | Existence check always true | absent-quote test: answer verified |
| C36 | Uncited claims allowed | uncited test: status not `UNCITED` |
| C37 | Judge result ignored | rejecting-judge test: answer verified |
