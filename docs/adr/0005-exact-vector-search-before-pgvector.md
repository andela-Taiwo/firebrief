# ADR 0005 — Exact vector search before pgvector

**Status:** Accepted · **Date:** 2026-11-09

## Context

Retrieval needs similarity search over chunk embeddings. The plan assumed pgvector with an
HNSW index.

Two facts changed that:

1. The pgvector image could not be pulled in this development environment (Docker's
   credential helper is broken here), so a pgvector-dependent test suite would be green in
   CI and red locally — the worst combination.
2. The corpus is two documents: a few hundred chunks. A linear scan over a few hundred
   vectors is sub-millisecond.

## Decision

Store embeddings as `double precision[]` and search exactly, with cosine similarity
computed in SQL. No extension, no index, no image dependency.

## Consequences

- Search is exact, which is simpler to reason about and to test.
- Cost grows linearly. At roughly ten thousand chunks this becomes noticeable; at a
  hundred thousand it is unacceptable.
- Adopting pgvector later is a migration: add the extension, add a `vector` column,
  backfill from the array. The chunk table's keys and semantics do not change.

## Revisit when

The corpus passes a few thousand chunks, or retrieval latency exceeds 100 ms at p95, or
the environment can run the pgvector image.
