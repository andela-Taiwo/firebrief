# hybrid-retrieval: find the sections a question is actually about

**Status:** In progress · **Branch:** `feat/hybrid-retrieval`
**Depends on:** `chunk-and-embed` · **Unblocks:** `answer-pipeline`, `citation-verifier`

## Goal

Given a question, return the handful of chunks most likely to contain the answer —
combining meaning-based and keyword-based search, because fire guidance mixes both:
"how wide can a dead end be?" is semantic, "BS 5839" is lexical — and measure how
often the right section is in the results.

## Scope

**In**
- Full-text search over chunks with a GIN index (`to_tsvector('english', heading_path || text)`).
- Exact cosine search over the stored vectors (ADR 0005).
- Reciprocal Rank Fusion to combine them, with the rank constant configurable.
- A result type that carries chunk, section, version, heading path, text and both ranks.
- A retrieval evaluation set with a recall@k script, so retrieval quality is a number
  rather than an opinion.

**Out (and where it goes)**
- Reranking and context packing: same feature, next PR if recall is adequate.
- Answer generation: `answer-pipeline` (F7).
- pgvector: still deferred (ADR 0005).

## Decisions & trade-offs

### D1. RRF rather than a weighted score sum
The two searches produce scores on incomparable scales: `ts_rank_cd` is heuristic,
cosine is bounded but not calibrated. RRF only uses ranks, so it needs no tuning of a
weight that would be fitted to a handful of queries.

| Option | For | Against |
|---|---|---|
| **Reciprocal Rank Fusion, k=60 (chosen)** | No score calibration; robust; one constant | Ignores how much better the top hit was |
| Weighted sum of normalised scores | Uses magnitude | The weights would be invented |

### D2. No semantic fake in production code
The hash-based `FakeEmbedder` is deterministic but meaningless for ranking. Tests of
ranking use a hashed bag-of-words embedder, which at least shares tokens with the query;
the fake stays for storage tests only.

### D3. Retrieval returns evidence, not answers
Every result carries the version and section, so a citation can name where it came from
and the verifier can check the claim against the exact text.

## Acceptance criteria

1. A question containing a distinctive term finds the section containing it.
2. A question that paraphrases a section still surfaces it through the vector side.
3. Fusion ranks a chunk found by both searches above one found by either alone.
4. Results are ordered deterministically when scores tie.
5. `limit` is respected and an empty query returns nothing rather than everything.
6. Recall@5 on the evaluation set is at least 0.8, asserted in a test.
7. A query with no matches returns an empty list, not an error.

## Test plan

A small corpus is ingested and embedded with the bag-of-words embedder, then queried.
The evaluation set is checked in and run by both a test and a `make eval-retrieval`
target, so a prompt or chunking change that hurts recall shows up as a number.

Canaries: remove the full-text side; remove the vector side; drop the GIN index and
confirm the plan still returns the same results (correctness, not speed).

## Risks

| Risk | Mitigation |
|---|---|
| Recall measured on six queries flatters itself | The set is checked in and grows with the corpus; the number is reported, not just asserted |
| Exact search slows as the corpus grows | ADR 0005 records the threshold to adopt pgvector |
| Fusion hides a broken side | Each side is tested independently before the fused result |

## Effort

3 dev-days, one PR.

## Build notes

- **Recall@3 = 1.00 (6/6)** on the checked-in set. That is a smoke gate, not a quality
  claim: six questions, three sections, a bag-of-words embedder. The number is printed by
  `make eval-retrieval` so it can be watched as the corpus grows.
- **`min_similarity` is 0.1 by default.** Without a floor, an unrelated query returned
  every chunk at cosine ~0 — the first version of the "no matches" test failed for that
  reason, which is the canary below.
- **The full-text index is excluded from autogenerate drift** (`include_object` in
  `migrations/env.py`) because it is an expression index created in raw SQL that
  Alembic cannot represent. Its behaviour is covered by the retrieval tests.

### A canary that found a gap

The first attempt at "remove the vector side" did not fail any test: the paraphrase query
`closing flat entrance door` was being satisfied by full-text search, because Postgres
splits the hyphen in `self-closing`. So the vector path had no test only it could pass.

Fixed by exposing `vector_search` and `text_search` and testing each on its own. The
canaries then failed as they should. This is the case for running canaries even when the
suite is green: it was green for the wrong reason.

## Canaries

| # | Break | Caught by |
|---|---|---|
| C29 | `vector_search` returns nothing | `test_the_vector_side_finds_a_chunk_on_its_own` |
| C30 | `text_search` returns nothing | `test_the_keyword_side_finds_a_chunk_on_its_own` |
| C31 | Cosine similarity inverted to distance | "no matches" test: unrelated chunks came back |
