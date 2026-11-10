# ADR 0008 — The redacted question is the one that may be stored

**Status:** Accepted · **Date:** 2026-11-10

## Context

A question can contain an email address, a phone number, a postcode or a card number. The
pipeline already redacts before the model call, but two copies of the raw question survived:
one in `AnswerResult.question`, which the audit log will persist, and one in the query
embedding, which is sent to a third party.

## Decision

- **Redact once, at the boundary.** `answer_question` redacts before anything leaves the
  process, including the embedding call. Retrieval, the prompt and the result all use the
  redacted text. There is no path where the raw question reaches a provider.
- **`AnswerResult.question` holds the redacted question.** That is the copy that may be
  stored, cached or logged. The caller already has what the reader typed, for display.
- **Findings carry kind and count, never the value.**

## Consequences

- Retrieval runs on redacted text. A postcode in a question stops being a search term,
  which is a small recall cost paid for not leaking it.
- A cache must be keyed on the redacted question, or a cache entry could hold personal
  data. Recorded for the semantic-cache work.
- The audit record can say "one email address was removed" but cannot reproduce what it
  was, by design.

## Scope of "guardrails"

This PR does pattern redaction. It does **not** implement prompt-injection detection on
input or retrieved text. The verifier is the defence that matters: a fabricated source
cannot verify, and an uncited instruction cannot be shown. If injection checks are added
later they belong with the verifier's evidence rules, not as a second guess about intent.

## Known gaps

Names and free-text addresses are not detected ("Flat C, 180 Albert Road" keeps everything
except a postcode), and obfuscated forms ("ada [at] example [dot] com") are not covered.
`redact` is a `Redactor`, so a stronger detector can be supplied per deployment without the
pipeline changing.


## Pattern order matters

Cards are checked before phones. A card group can start with `0` — in
`4000 0566 5566 5556` the run `0566 5566 5556` matches the phone pattern, so a phone-first
pass would redact half the card, report the wrong kind and leave `4000` in the text. The
phone pattern also refuses to start inside a longer digit run, and the postcode pattern
refuses ordinals (`B1 1st`, `L2 2nd`) so guidance language is not mistaken for a postcode.

`answer_from_sources` always redacts internally and takes only the question: a caller cannot
supply a redaction for different text. Redaction is idempotent, which is what makes the
second pass in `answer_question` harmless.
