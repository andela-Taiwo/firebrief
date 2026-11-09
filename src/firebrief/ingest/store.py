"""Idempotent, append-only storage for the corpus.

Version identity is the hash of the *parsed sections*, not the raw bytes. GOV.UK
pages change bytes for reasons that are not guidance: cookie banners, CSRF
tokens, "last updated" stamps, analytics snippets. Hashing the raw page would
create a version and a re-embed on every fetch. The raw bytes are still recorded,
as `source_sha256`, so the evidence is not lost.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
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


def content_hash(sections: Sequence[ParsedSection]) -> str:
    """Stable identity for the guidance itself, independent of page furniture."""
    payload = json.dumps(
        [[section.heading_path, section.heading, section.body] for section in sections],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def ingest(session: AsyncSession, document: SourceDocument) -> IngestResult:
    licence = check_licence(document.licence)
    sections = parse_sections(document.html, title=document.title)
    content = content_hash(sections)
    source = source_hash(document.html)

    # Lock the document row: two workers ingesting the same slug serialise here,
    # so the second sees the first's version instead of racing the unique key.
    stored = await session.scalar(
        select(Document).where(Document.slug == document.slug).with_for_update()
    )
    if stored is None:
        stored = Document(slug=document.slug, title=document.title, source_url=document.source_url)
        session.add(stored)
        await session.flush()
    else:
        stored.title = document.title
        stored.source_url = document.source_url

    existing = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == stored.id, DocumentVersion.content_hash == content
        )
    )
    if existing is not None:
        return IngestResult(slug=document.slug, version_id=existing.id, created=False, sections=0)

    version = DocumentVersion(
        document_id=stored.id,
        content_hash=content,
        source_sha256=source,
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
