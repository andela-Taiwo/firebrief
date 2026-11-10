# chunk-and-embed: turn sections into retrievable, embedded chunks

**Status:** In progress · **Branch:** `feat/chunk-and-embed`
**Depends on:** `corpus-ingestion` · **Unblocks:** `hybrid-retrieval`

## Goal

Every section of every stored version becomes one or more chunks small enough to fit a
retrieval context window, each embedded with a pinned model and traceable back to the
version and heading path it came from — and re-running the job never duplicates a chunk.

## Scope

**In**
- Chunking that respects section boundaries, splits long sections on word boundaries with
  overlap, and keeps the heading path on every chunk.
- An `Embedder` port with a deterministic fake (tests, offline) and an OpenAI adapter.
- A `chunks` table keyed by `(version_id, embedding_model, ordinal)`, storing the vector
  as `double precision[]` with an exact cosine-search helper.
- Idempotent `embed_version`, and re-embedding under a new model as a separate, additive
  set rather than a destructive update.

**Out (and where it goes)**
- Vector indexing and hybrid search: `hybrid-retrieval` (F5).
- Reranking and context packing: F5.
- PDF chunking: blocked on ADR 0004.

## Decisions & trade-offs

### D1. No pgvector yet
The plan assumed pgvector, but the image cannot be pulled in this environment (Docker's
credential helper fails), and a two-document corpus is a few hundred chunks. Exact cosine
search in SQL is accurate and fast enough at this size.

| Option | For | Against |
|---|---|---|
| **`double precision[]` + exact search (chosen)** | No extension, works everywhere, exact | Linear scan; unusable beyond tens of thousands of chunks |
| pgvector + HNSW | Scales | Needs an extension and an image this environment cannot fetch |

Revisit at F5, or sooner if the corpus grows past a few thousand chunks. Recorded in
ADR 0005.

### D2. Chunk by section, then by size
Sections are already the unit a citation points at. A section that fits becomes one chunk;
a longer one is split on word boundaries with overlap, and every piece keeps the path.

### D3. Model is part of the key
Re-embedding with a new model must not delete the old vectors while retrieval still uses
them. Chunks are keyed by `(version_id, embedding_model, ordinal)`, so switching model is
additive and reversible.

## Acceptance criteria

1. A section under the token budget becomes exactly one chunk, with its heading path.
2. A longer section becomes several chunks, each within the budget, with overlapping text
   so a sentence is not cut in half without context.
3. Re-running `embed_version` adds no rows.
4. Embedding under a second model adds a second set and leaves the first intact.
5. Every chunk traces to a version and an ordinal; no chunk exists without them.
6. The runtime role can read chunks and cannot write them.
7. Migrations go up, down and back up with no drift.

## Test plan

Chunker and embedder are pure and tested without a database. Storage is tested against
real PostgreSQL, as everything else is. Fake embedder everywhere: no network, no cost.

Canaries: remove the uniqueness on `(version_id, model, ordinal)`; drop the heading path
from chunks; make the chunker ignore the token budget.

## Risks

| Risk | Mitigation |
|---|---|
| Chunks too small to be useful | Budget and overlap are configuration, tested at the boundary |
| Re-embed silently overwrites | Model is in the key; a test asserts the first set survives |
| Exact search becomes slow | Recorded in ADR 0005 with a size trigger to adopt pgvector |

## Effort

3 dev-days, one PR.

## Build notes

- **No pgvector** (ADR 0005): the image cannot be pulled in this environment, and the corpus
  is a few hundred chunks. Exact cosine search is the retrieval path until the corpus grows.
- **Chunk budget** is 300 tokens with 50 tokens of overlap by default, both configuration.
  `token_estimate` is stored per chunk so packing can budget without re-counting.
- **Model in the key** means re-embedding is additive. Nothing deletes an old model's chunks,
  which is deliberate: retrieval must never lose the vectors it is currently using.

## Canaries

| # | Break | Caught by |
|---|---|---|
| C23 | Uniqueness on `(version_id, model, ordinal)` dropped | re-embed test: `ON CONFLICT` has no matching constraint, so ingestion fails loudly rather than duplicating (caught, though as an error rather than a duplicate) |
| C24 | Chunker stops respecting the token budget | budget test: one chunk where several were expected |
| C25 | `chunks` not added to the reviewed global list | the invariant test failed the moment the table was created, which is exactly the design |

## Review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | Chunks could not be traced to their section; `heading_path` is not unique | `section_id` foreign key plus `char_start`/`char_end` into the section body. The two "Notes" sections in the fixture resolve to different ids and different text |
| **Must** | Changing chunk settings silently mixed sets | The chunker configuration is part of the key (`words-v1:300/50`), so a new budget produces a complete second set; tested with two configurations |
| **Must** | `embed_version` returned work it had not done | It returns `EmbedResult(created, existing)`, counted from `RETURNING`; the re-embed test asserts `created == 0` |
| Should | Embedding bypassed the budget and was sent whole | Inputs are batched at 64. **Spend is not yet charged to a budget** — the corpus is global, not tenant-owned, so there is no budget to charge. Recorded as a follow-up for the ingestion operator job, not silently skipped |
| Should | `OpenAIEmbedder` sent no key | The key is a constructor argument and is sent as a Bearer header; request shape, header and `index` ordering are tested with `MockTransport` |
| Should | No vector validation | Count, dimensions and NaN/inf are checked before writing; `dimensions` is a column with a check constraint that the array length matches |
| Should | Only the body was embedded | The embedding input is `heading_path + "\n\n" + text`, while `text` stores the body alone. Measuring the difference belongs to the evaluation harness |
| Test gap | Overlap test used substring matching | Compares word lists and asserts the exact configured overlap |
| Test gap | No wrong-count, dimension, long-section or long-word tests | Added, including an end-to-end split of a 600-word section |
| Minor | Quadratic splitting | The window measures characters, not re-joined strings |
| Minor | One insert per chunk | A single multi-row insert |
| Minor | `.unique()` was unnecessary | Removed |
| Deferred | Sentence and row boundaries | Still word-based; recorded as a quality follow-up |
| Deferred | Semantic `FakeEmbedder` | The hash fake is deterministic but meaningless for ranking; retrieval tests in F5 need a hashed bag-of-words fake |

### Canaries added

| # | Break | Caught by |
|---|---|---|
| C26 | Every chunk points at the first section | "Notes" test: `first_id != second_id` |
| C27 | Chunker configuration removed from the key | second configuration reports `created == 0` |
| C28 | `created` reports all chunks rather than inserted ones | re-embed test: `6 == 0` fails |
