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
