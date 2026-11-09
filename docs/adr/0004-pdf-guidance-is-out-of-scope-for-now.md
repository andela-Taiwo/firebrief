# ADR 0004 — PDF guidance is out of scope for the first corpus

**Status:** Accepted · **Date:** 2026-11-09

## Context

Approved Document B is published as a PDF attachment, not as HTML. The ingestion
pipeline parses HTML: it needs headings to build section paths and text to cite.

## Decision

The first corpus contains HTML guidance only. A document whose only available form is
a PDF is not ingested, and is not listed in `corpus/sources.toml`.

Ingestion refuses unlisted slugs, so an attempt to add ADB now fails loudly rather than
storing a stub that cannot be cited.

## Why not a PDF parser now

PDF text extraction loses the heading structure that citations depend on, and it
introduces page-number and column-order problems. Doing it badly would produce
confident citations to the wrong paragraph, which is the failure this product exists to
avoid. It deserves its own feature with its own evaluation, not a hurried adapter.

## Consequences

- Answers about Approved Document B are out of scope until a PDF pipeline exists.
- The retrieval layer must not pretend otherwise: a question with no retrieved section
  is a refusal, not a guess.
- `sources.toml` is the single place that decides what is in the corpus, so adding ADB
  later is a manifest change plus a parser, not a rewrite.

## Revisit when

A PDF ingestion feature is planned, with a layout-aware parser and a section-boundary
evaluation set built from a handful of real pages.
