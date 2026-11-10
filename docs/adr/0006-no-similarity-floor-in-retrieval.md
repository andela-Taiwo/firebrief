# ADR 0006 — No similarity floor in retrieval

**Status:** Accepted · **Date:** 2026-11-10

## Context

Retrieval can filter vector results by cosine similarity. A floor looks appealing: it
would stop unrelated chunks being returned for a question nothing covers.

It does not work as a relevance test. Cosine similarity depends on the embedding model:
a hash-based fake gives unrelated text a score near zero, while a real model gives
unrelated prose 0.2–0.4. A single number would be either useless for one model or
destructive for the other, and calibrating it per model requires labelled data that does
not exist yet.

## Decision

`min_similarity` defaults to **no floor**. Retrieval returns its best candidates and says
how each was ranked. Deciding whether the evidence supports an answer is the answer
pipeline's job, where a citation must be verified against the source text, and a refusal
is an explicit outcome rather than a threshold.

The parameter remains, so an evaluation can measure what a floor would cost.

## Consequences

- A question the corpus does not cover still returns candidates. That is deliberate: the
  refusal must be justified by evidence, not by a similarity score.
- Every retrieved result carries `vector_rank` and `text_rank`, so a later relevance
  judgement has something to reason about.
- Query embedding cost is not yet metered. Retrieval has no tenant context; the answer
  pipeline will call it inside a tenant request and charge the embedding there.

## Revisit when

The evaluation set is large enough to calibrate a per-model floor, or the answer pipeline
shows refusals that a floor would have prevented.
