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

## Build notes (added during build)

- **Writer role.** Ingestion writes as the owner/worker role, never as the runtime role. The
  runtime role has `SELECT` only on the three corpus tables, which is what the API will need and
  nothing more. There is no CLI to run ingestion yet; it is called from a test and will be called
  from an operator command in F3.1.
- **Concurrent ingestion.** Two workers ingesting the same document at once would race on
  `uq_document_versions_sha`; the loser gets an integrity error rather than a duplicate. The
  worker is single-process today, so this is recorded rather than handled.
- **Unchanged bytes still refresh title and URL.** The version and sections are untouched, but
  `documents.title` and `documents.source_url` are updated, so a corrected title propagates
  without a new version. Worth revisiting if the title is ever used in a citation.

## Review responses

| Sev | Finding | Response |
|---|---|---|
| **H1** | Runtime write test could pass on a foreign-key error | The insert now selects a real `version_id` and asserts `permission denied`; `has_table_privilege` checks INSERT/UPDATE/DELETE/TRUNCATE on all three tables |
| **H2** | Hashing raw bytes would churn on page furniture | Version identity is now the hash of the parsed sections; the raw bytes are kept as `source_sha256`. Test: a page differing only in cookie banner, script and nav creates no version |
| **H3** | No rule for the current version | `select_current(versions, as_of)` in `firebrief/ingest/current.py`: latest `effective_from` in force on the date, `fetched_at` breaking ties. Tested for before/between/after and for a same-edition correction |
| **H4** | Pre-heading text was silently dropped | Parsing is limited to `<main>`; text before the first heading becomes an Introduction section. Tested, along with a page that has no headings at all (one introduction) and an empty page (refused) |
| M | Append-only only holds against the runtime role | Recorded in ADR 0003, with the dedicated ingest role as the follow-up |
| M | `documents` not covered | Tested: the title may change, deletion is refused by the foreign key from versions |
| M | Concurrent ingests | The document row is locked with `SELECT ... FOR UPDATE`, so a second worker sees the first's version; the unique constraint remains the backstop |
| M | Licence check was a prefix match in the test | Tests now assert exact allowlist membership and include `ogl-3.0-extra` and `OGL` as near misses |
| M | Parser coverage | Fixtures now include script, style, cookie banner and footer; table content in reading order; duplicate headings kept as separate sections |

### Canaries added

| # | Break | Caught by |
|---|---|---|
| C14 | `GRANT INSERT ON documents TO firebrief_app` | privilege test names `ins` |
| C15 | Content hash reverted to the raw bytes | furniture-change test fails |
| C16 | Licence check weakened to `startswith("ogl")` | near-miss test: "DID NOT RAISE LicenceNotAccepted" |
