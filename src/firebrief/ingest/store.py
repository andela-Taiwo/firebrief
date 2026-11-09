"""Idempotent, append-only storage for the corpus.

Version identity is the hash of the *parsed sections* plus the reviewed metadata
(licence and edition). Hashing the raw page would create a version, and a
re-embed, every time a cookie banner or CSRF token changed; ignoring the metadata
would silently drop a corrected edition. The raw bytes are kept as
`source_sha256` so the evidence is not lost.

Insert-or-ignore with `on conflict do nothing returning` makes two workers
ingesting the same document converge on one version instead of racing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.db.models import Document, DocumentVersion, Section
from firebrief.ingest.licence import check_licence
from firebrief.ingest.parse import parse_sections
from firebrief.ingest.types import ParsedSection, SourceDocument


@dataclass(frozen=True, slots=True)
class IngestResult:
    slug: str
    version_id: uuid.UUID
    created: bool
    sections: int


def source_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def content_hash(
    sections: Sequence[ParsedSection],
    *,
    licence: str,
    edition: str,
    effective_from: date | None,
) -> str:
    """Identity of the guidance and the reviewed statement about it."""
    payload = json.dumps(
        {
            "licence": licence,
            "edition": edition,
            "effective_from": effective_from.isoformat() if effective_from else None,
            "sections": [
                [section.heading_path, section.heading, section.body] for section in sections
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def ingest(session: AsyncSession, document: SourceDocument) -> IngestResult:
    licence = check_licence(document.licence)
    sections = parse_sections(document.html, title=document.title)
    content = content_hash(
        sections,
        licence=licence,
        edition=document.edition,
        effective_from=document.effective_from,
    )
    source = source_hash(document.html)

    # Serialise ingestion per document. The on-conflict inserts are the backstop;
    # this is what makes two workers converge instead of one losing a race.
    await session.execute(
        text("select pg_advisory_xact_lock(hashtext(:slug))"), {"slug": document.slug}
    )

    stored_id = await session.scalar(
        insert(Document)
        .values(slug=document.slug, title=document.title, source_url=document.source_url)
        .on_conflict_do_nothing(index_elements=["slug"])
        .returning(Document.id)
    )
    if stored_id is None:
        stored_id = await session.scalar(select(Document.id).where(Document.slug == document.slug))
    if stored_id is None:
        raise RuntimeError(f"could not create or find the document {document.slug!r}")

    # Only write when something actually changed, so a no-op ingest leaves
    # documents.updated_at alone.
    current = (
        await session.execute(
            select(Document.title, Document.source_url).where(Document.id == stored_id)
        )
    ).one()
    if current.title != document.title or current.source_url != document.source_url:
        await session.execute(
            update(Document)
            .where(Document.id == stored_id)
            .values(title=document.title, source_url=document.source_url)
        )

    version_id = await session.scalar(
        insert(DocumentVersion)
        .values(
            document_id=stored_id,
            content_hash=content,
            source_sha256=source,
            title=document.title,
            fetched_at=document.fetched_at,
            licence=licence,
            edition=document.edition,
            effective_from=document.effective_from,
        )
        .on_conflict_do_nothing(index_elements=["document_id", "content_hash"])
        .returning(DocumentVersion.id)
    )

    if version_id is None:
        existing_id = await session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == stored_id,
                DocumentVersion.content_hash == content,
            )
        )
        if existing_id is None:
            raise RuntimeError(f"{document.slug!r}: conflict but no stored version")
        count = await session.scalar(
            select(func.count()).select_from(Section).where(Section.version_id == existing_id)
        )
        return IngestResult(
            slug=document.slug, version_id=existing_id, created=False, sections=int(count or 0)
        )

    session.add_all(
        [
            Section(
                version_id=version_id,
                ordinal=index,
                heading_path=section.heading_path,
                heading=section.heading,
                body=section.body,
            )
            for index, section in enumerate(sections)
        ]
    )
    await session.flush()

    return IngestResult(
        slug=document.slug, version_id=version_id, created=True, sections=len(sections)
    )
