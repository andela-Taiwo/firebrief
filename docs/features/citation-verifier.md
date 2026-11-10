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

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | A quote was accepted if it existed in *any* cited source, not the one it cites | Quotes are attributed to the marker that follows them (or the preceding one), and existence is checked only in that source. Tested with the quote present in [2] but cited as [1] |
| **Must** | Without a judge, a contradiction verified | `judge` is now a required keyword argument, and a failing judge withholds. The "ten metres" contradiction is tested with a rejecting judge |
| **Must** | Judge failures escaped | `supports` is wrapped; a timeout becomes `JUDGE_ERROR` and withholds |
| **Must** | Trivial quotes proved nothing | A quote needs at least six words; `"must be"` is refused with `QUOTE_TOO_SHORT` |
| **Must** | The judge saw the source's own words inside the claim | The judge receives the claim with quotes removed, the quote, and a ±200 character window around the match. Asserted directly on the judge's arguments |
| **Must** | Multiple markers were checked as "every quote in every source" | Each marker occurrence needs its own quote; `[1][2]` with one quote withholds, and `[1][1]` with one quote withholds |
| Should | Sentence splitting broke multi-sentence quotes and abbreviations | Quotes are masked before splitting, and common abbreviations are protected |
| Should | Matching ignored word boundaries | Quotes are matched as a contiguous run of tokens, so `metre` does not match inside `metres` |
| Should | Typography was not normalised | NFKC plus a mapping for curly quotes, apostrophes, dashes and non-breaking spaces |
| Should | The judge was not recorded | `Verification` carries `judge_model` and `judge_prompt_version` |
| Minor | Checks lacked section, version and offsets | `ClaimCheck` carries `section_id`, `version_id`, `char_start`, `char_end` |
| Minor | Answer noise became UNCITED claims | Still withheld; the answer format is pinned by the generation prompt's contract, tested against `"<quote>" [n]` |
| Decision | Elisions in quotes | Spliced quotes are not accepted: a quote is matched as a contiguous run, so `"..."` inside it fails existence |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C38 | Existence searched every source | wrong-source test verifies |
| C39 | Judge exception propagates | `TimeoutError` escapes `verify_answer` |
| C40 | Minimum quote length removed | trivial-quote test verifies |

## Re-review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | Offsets pointed into the normalised string, so a ligature or superscript shifted the highlight | Tokens are found in the original text and normalised one at a time, so offsets are original offsets. Spans also include the trailing punctuation the quote ends with. Tested with `ﬁ` and `m²` before the passage: `source.text[start:end]` equals the quote |
| **Must** | Curly-quoted multi-sentence passages were split mid-quote | Typography is translated before masking and splitting. Tested with `“First sentence. Second sentence.” [1]` |
| **Must** | One parse test was a tautology | Exact assertions: `claims[1].text == "Two thing."`, `claims[1].quotes == ((1, DEAD_ENDS),)` |
| Should | Abbreviation masking was case-sensitive and matched inside words | One word-bounded, case-insensitive regex; tested with a capitalised `E.g.` |
| Should | `UNATTRIBUTED` was unreachable | Removed from the enum and the branch |
| Should | Judge errors were swallowed silently | The error type is recorded on the check and logged with the chunk id; tested |
| Should | Judge calls run sequentially | **Deferred.** Recorded here rather than half-implemented: concurrency needs a semaphore and, once the real judge lands, budget accounting, which belongs with the judge integration |
| Note | Prompt must tell the model to quote in context, reserve quotes for evidence, and avoid elisions | Captured in the plan's decisions and for the answer-pipeline prompt |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C41 | Tokens found in the normalised string | offsets test: slice no longer equals the quote |
| C42 | Curly quotes not translated before splitting | multi-sentence curly-quote test |
| C43 | Abbreviation masking removed | capitalised `E.g.` splits the claim |
