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

## Implementation review responses

| Sev | Finding | Response |
|---|---|---|
| **H1** | The licence gate only ever saw the adapter's default | `corpus/sources.toml` is the reviewed manifest: licence, edition and effective date per slug. The adapter refuses unlisted slugs before any network call, and metadata comes from the manifest, not the page |
| **H2** | Intro text lost; title missing from the path | The title seeds the heading path, so a govspeak body with no h1 still cites as "Title > Section", and pre-heading text becomes an introduction. Tested with a content-API-shaped fixture |
| **H3** | Table cells ran together | Cell, row and block boundaries now emit separators; `Door type \| Rating` and `Flat entrance \| FD30S` are asserted |
| **H4** | The adapter missed `details.parts[]` and PDFs | Parts are joined with their titles; PDFs are excluded by decision in ADR 0004, and an unlisted PDF-bearing document cannot be ingested at all |
| **H5** | `effective_to` cannot be set on an immutable row | The column is gone. The current version is the latest `effective_from` at or before the date, with `fetched_at` breaking ties |
| M | Version identity ignored the reviewed metadata | Licence and edition are part of the content hash, so a corrected edition is a new version rather than a silent no-op; tested |
| M | Check-then-insert race | `insert ... on conflict do nothing returning` for documents and versions |
| M | TRUNCATE bypassed the guard | `before truncate ... for each statement` triggers on all three tables. The test reset uses `session_replication_role = replica`, which is the owner bypass ADR 0003 records |
| M | Runtime write test could depend on error ordering | It asserts `permission denied` explicitly |
| L | Long headings would raise | `heading` and `heading_path` are `Text` |
| L | `sections=0` for an existing version | Returns the stored section count |
| L | Versions did not record their title | `document_versions.title` snapshots it, so an old citation keeps its name |
| L | No User-Agent or retries | User-Agent added; retries deferred and noted in the code |

### Canaries added by this round

| # | Break | Caught by |
|---|---|---|
| C17 | Manifest returns a default for unlisted slugs | `test_an_unlisted_document_is_refused`: DID NOT RAISE |
| C18 | Version identity ignores licence and edition | corrected-edition test fails |
| C19 | `sections_no_truncate` dropped | truncate test: DID NOT RAISE |

### Note on the migration

`0006_corpus` was edited rather than superseded, because the branch is unmerged and the
schema changed shape (title snapshot, no `effective_to`, `Text` headings, truncate
guards). The local test database was rebuilt from an empty schema rather than patched,
because the previous migration had already been applied here.

## Final review responses

| Severity | Finding | Response |
|---|---|---|
| **Must** | Part titles emitted as `<h2>`, so a part's own subheading popped the part off the path | Part titles are `<h1>`, one level above body headings. End-to-end test: `Document > Part one > Sub` |
| Should | A corrected `effective_from` was a silent no-op | It is part of the content hash, with a test alongside the corrected-edition one |
| Should | No-op ingests still wrote `documents` | The row is updated only when title or source URL changed; `updated_at` is asserted unchanged |
| Should | Manifest not validated at load | `check_licence` runs per entry and a non-date `effective_from` is rejected, each with a test |
| Should | No concurrency test | Two sessions with `asyncio.gather`: one `created=True`, one version, one set of sections. `pg_advisory_xact_lock` per slug makes it deterministic; on-conflict stays as the backstop |
| Should | Title de-duplication was exact-match | Compared with `casefold()`, so a page that differs in case cannot produce `Title > Title` |
| Minor | Manifest paths were working-directory relative and loaded at import | Resolved from `__file__` and loaded in a fixture |
| Minor | Unlisted-slug test used a real client | `MockTransport` that fails the test on any request |
| Minor | No test for `effective_from = None` | Treated as the earliest; tested against a dated version |
| Minor | `require_main` matched `<main-menu>` | Matches `<main` followed by whitespace or `>` |
| Minor | PDF decision record | ADR 0004 covers Approved Document B explicitly |

### Canaries added

| # | Break | Caught by |
|---|---|---|
| C20 | `effective_from` dropped from the content hash | corrected-date test fails |
| C21 | `documents` updated unconditionally | `updated_at` test fails |
| C22 | Manifest licence check removed | refused-licence manifest test: DID NOT RAISE |
