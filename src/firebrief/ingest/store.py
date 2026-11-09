"""Idempotent, append-only storage for the corpus.

The hash of the fetched bytes is the identity of a version. Re-ingesting the
same bytes changes nothing; different bytes become a new version and the old one
stays readable, so every citation can be traced to what was actually read.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.db.models import Document, DocumentVersion, Section
from firebrief.ingest.licence import check_licence
from firebrief.ingest.parse import parse_sections
from firebrief.ingest.types import SourceDocument


@dataclass(frozen=True, slots=True)
class IngestResult:
    slug: str
    version_id: uuid.UUID
    created: bool
    sections: int


def content_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


async def ingest(session: AsyncSession, document: SourceDocument) -> IngestResult:
    licence = check_licence(document.licence)
    sections = parse_sections(document.html)
    digest = content_hash(document.html)

    stored = await session.scalar(select(Document).where(Document.slug == document.slug))
    if stored is None:
        stored = Document(slug=document.slug, title=document.title, source_url=document.source_url)
        session.add(stored)
        await session.flush()
    else:
        stored.title = document.title
        stored.source_url = document.source_url

    existing = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == stored.id, DocumentVersion.sha256 == digest
        )
    )
    if existing is not None:
        return IngestResult(slug=document.slug, version_id=existing.id, created=False, sections=0)

    version = DocumentVersion(
        document_id=stored.id,
        sha256=digest,
        fetched_at=document.fetched_at,
        licence=licence,
        edition=document.edition,
        effective_from=document.effective_from,
        effective_to=document.effective_to,
    )
    session.add(version)
    await session.flush()

    session.add_all(
        [
            Section(
                version_id=version.id,
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
        slug=document.slug, version_id=version.id, created=True, sections=len(sections)
    )
