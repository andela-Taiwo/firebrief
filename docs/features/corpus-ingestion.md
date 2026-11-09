# corpus-ingestion: a versioned, licence-checked snapshot of the guidance

**Status:** In progress · **Branch:** `feat/corpus-ingestion`
**Depends on:** `tenant-isolation` · **Unblocks:** `chunk-and-embed`, `hybrid-retrieval`

## Goal

A reproducible snapshot of the public guidance Firebrief answers from, where every section
can be traced to the exact bytes, licence and edition it came from, and where re-running
ingestion cannot duplicate or silently rewrite history.

## Scope

**In**
- A `DocumentSource` port, a GOV.UK Content API adapter and a fake source for tests.
- A structure-aware HTML parser: headings become section boundaries, each section keeps its
  heading path.
- A licence gate: only Open Government Licence documents are accepted, checked per document.
- Versioned storage keyed by the SHA-256 of the fetched bytes: identical bytes are a no-op,
  changed bytes become a new version, and old versions are never modified.
- Append-only enforcement on versions and sections, by trigger.

**Out (and where it goes)**
- Chunking and embeddings: `chunk-and-embed` (F4).
- Retrieval: `hybrid-retrieval` (F5).
- A reviewed manifest of every document with its edition and effective dates: F3.1, once the
  first ten documents are chosen.

## Decisions & trade-offs

### D1. Version by content hash, not by fetch time
Re-running ingestion on an unchanged page must change nothing. The hash is the identity of the
bytes; the fetch time is metadata on the version.

| Option | For | Against |
|---|---|---|
| **SHA-256 of the body (chosen)** | Idempotent; proves what was read | A whitespace-only change creates a version |
| Timestamp or `updated_at` from the page | Fewer versions | The page can change without its timestamp, and the timestamp can change without the content |

### D2. The corpus is global, not tenant-owned
Guidance is public and shared by every tenant, so these tables are on the reviewed global list
alongside `alembic_version`. The invariant test enforces that each new table is a deliberate
choice, and the runtime role gets read-only access.

### D3. Stdlib HTML parsing, no new dependency
The parser only needs heading structure and text. `html.parser` is enough, and a DOM library
would be a dependency to justify for a job it does not do better.

### D4. Licence is data, checked at ingestion
Each source document declares its licence; ingestion refuses anything not on the allowlist.
British Standards are never fetched, and the refusal is tested rather than assumed.

## Acceptance criteria

1. Re-ingesting identical bytes creates no new document version and no new sections.
2. Changed bytes create a new version; the previous version and its sections remain readable.
3. A document whose licence is not on the allowlist is refused and nothing is stored.
4. Sections follow heading structure and carry a heading path.
5. `UPDATE` or `DELETE` on a version or a section fails, whatever the role.
6. The runtime role can read the corpus and cannot write it.
7. The corpus tables are on the reviewed global list, and the invariant test passes.
8. Migrations go up, down and back up with no drift.

## Test plan

Written first, against fixtures: two real-shaped GOV.UK HTML pages, one licence-refused document,
one changed-content pair. The fake source means no network in tests.

Canaries: drop the append-only trigger; widen the licence allowlist; remove the corpus tables
from the reviewed list; re-ingest and assert no duplicate.

## Risks

| Risk | Mitigation |
|---|---|
| GOV.UK markup changes and the parser silently produces empty sections | Refuse a version with zero sections; assert section count in tests |
| A document is re-published under a different URL | Slug is the identity; a URL change is a new version of the same slug |
| Licence drift | Licence is checked per document at ingestion and stored with the version |

## Effort

4 dev-days, one PR.
