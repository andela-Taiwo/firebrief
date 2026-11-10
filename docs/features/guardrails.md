# guardrails: nothing personal leaves for the model

**Status:** In progress · **Branch:** `feat/guardrails`
**Depends on:** `answer-pipeline` · **Unblocks:** the API

## Goal

A question that contains a name, an address, a phone number or a card number is answered
without those details being sent to a model provider. Redaction happens on the way to the
model, and the record of what was redacted holds the kind, never the value.

## Scope

**In**
- A redactor for the patterns people actually paste: email, UK phone, UK postcode, UK
  national insurance number, and long digit strings that look like card numbers.
- Findings that record the kind and the count, never the matched text.
- Integration in the pipeline: retrieval uses the original question, the *prompt* uses the
  redacted one, and the result carries what was removed.
- Tests for each pattern, for false positives on the corpus vocabulary, and for the
  integration.

**Out (and where it goes)**
- A general DLP classifier: this is pattern redaction, and pretending otherwise would be
  worse than saying what it does.
- Redacting retrieved evidence: the corpus is public guidance and contains no personal data.

## Decisions & trade-offs

### D1. Retrieve on the original, prompt on the redacted
Redacting before retrieval would search for `[REDACTED:POSTCODE]` and find nothing. The
question only leaves the process at the model call, so that is where redaction belongs.

### D2. Findings never contain the value
A redaction log that stores the thing it redacted is a new copy of the secret. Findings
carry the kind and a count; the audit record says "one email address was removed", not
which one.

### D3. Conservative patterns, explicit gaps
The patterns cover what people paste into a fire-safety question. Names and free-text
addresses are not detected, and the documentation says so rather than implying full DLP.

## Acceptance criteria

1. An email address in a question is replaced before the prompt is built.
2. A UK postcode, phone number and NI number are each replaced.
3. A long digit string that looks like a card number is replaced.
4. The corpus vocabulary ("thirty metres", "FD30S", "BS 5839") is untouched.
5. Findings record kind and count, never the value.
6. The retrieved sources still come from the original question.
7. `AnswerResult` carries the findings for the audit log.

## Test plan

Pure tests per pattern and per false positive; one pipeline test proving the provider
receives the redacted text and the result records the finding.

Canaries: redact before retrieval; store the matched value in the finding; drop the
redaction from the prompt.

## Risks

| Risk | Mitigation |
|---|---|
| Over-redaction makes the question meaningless | Patterns are narrow; a test asserts the corpus vocabulary survives |
| A false sense of DLP | The docstring and the plan say what is not covered |

## Effort

1.5 dev-days, one PR.

## Build notes

- **Redaction happens at the prompt, not at retrieval.** The question is used unaltered to
  search, and only the copy that goes to the model is redacted. Redacting earlier would
  search for `[REDACTED:postcode]` and find nothing.
- **Findings carry a kind and a count.** Not the value, not a position: a log that stores
  the thing it removed is a second copy of it.
- **Known gaps, stated:** names and free-text addresses are not detected. This is pattern
  redaction and the docstring says so. Claiming more would be worse than claiming less.
- **Every refusal carries the findings too**, so the audit record can say what was removed
  even when no model was called.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C58 | The prompt is built from the raw question | pipeline redaction test |
| C59 | A finding is fabricated with the text length as its value | findings test |
| C60 | The card pattern widened to any digit run | corpus vocabulary test (`BS 5839`) |

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | The raw question still left the process — the query embedding sends it to a provider | Redaction moved to the boundary: `answer_question` redacts **before** retrieval, so the embedder, the prompt and the result all use the redacted text. A recording embedder test asserts the email never reaches it |
| **Must** | The raw question would be persisted by the audit log | `AnswerResult.question` is the redacted question; the caller keeps what the reader typed. Recorded in ADR 0008 |
| Should | Bracketed and dotted UK phone formats leaked | Optional opening bracket, `(0)` after `+44`, `.` as a separator; each format tested, and a whole-string assertion catches a stray bracket left behind |
| Should | NI numbers were case-sensitive | `re.IGNORECASE`, tested lowercase |
| Should | Any 13–19 digit run was treated as a card | Luhn check; a same-length reference number is left alone |
| Should | False positives untested against guidance text | Dimensions, `BS EN 1634-1:2014`, `BS 9991:2015`, `Category L1`, `30 minutes`, `10/11/2026`, `Regulation 38` and `SI 2005/1541` all survive |
| Should | `assert text not in result.text` was nearly always true | Each test now asserts the specific value is gone and the specific mask is present |
| Should | `type(result.findings[0])(...)` hid the type | `Finding` imported and constructed directly |
| Should | Kinds were only tested one at a time | Email, phone and postcode together, pinning the pattern order |

### Recorded for later

- **Prompt-injection scope** is settled in ADR 0008: the verifier is the defence, and
  intent-guessing is not added.
- **A stronger detector** can be supplied through the `Redactor` interface (Presidio or an
  NER service) without the pipeline changing.
- **The semantic cache** must be keyed on the redacted question, or an entry could hold
  personal data.
- **Metrics**: redaction counts per kind, never values.
- **Known gaps** in the docstring: names, free-text addresses, obfuscated forms.

### Canaries

| # | Break | Caught by |
|---|---|---|
| C61 | Embedding uses the raw question | recording-embedder test |
| C62 | Luhn check removed | long-reference test |
| C63 | NI pattern case-sensitive | lowercase NI case |
| C64 | Opening bracket not part of the phone match | whole-string phone test |


## Re-review 2 responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | The phone pattern could cut a card in half, reporting the wrong kind | Cards run first, before phones, and the phone pattern refuses to start inside a longer digit run. `4000 0566 5566 5556` is now one CARD finding with nothing left behind |
| Should | Ordinals look like postcodes (`B1 1st`) | The guard sits after the digit (`\d(?!st|nd|rd|th)[A-Z]{2}`), tested against four floor and requirement phrasings |
| Should | `answer_from_sources` took both a question and a redaction | It takes only the question and redacts internally, so a mismatched redaction cannot be passed. Idempotence is tested |
| Should | The ADR was missing | ADR 0008 records storage minimisation, patterns-not-DLP, the known gaps, how prompt injection is handled, and why pattern order matters |

### Canaries

| # | Break | Caught by |
|---|---|---|
| C65 | Phones checked before cards | zero-leading card test |
| C66 | Ordinal guard removed | floor and requirement negatives |
