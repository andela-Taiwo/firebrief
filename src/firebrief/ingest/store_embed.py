"""Chunk and embed a stored version.

Idempotent: re-running adds nothing. Additive: a second model produces a second
set of chunks, and the first stays intact.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.db.models import Chunk, Section
from firebrief.ingest.chunk import DEFAULT_MAX_TOKENS, DEFAULT_OVERLAP_TOKENS, chunk_sections
from firebrief.ingest.embed import Embedder
from firebrief.ingest.types import ParsedSection


class VersionNotFound(Exception):
    """No such version, or it has no sections."""


async def embed_version(
    session: AsyncSession,
    version_id: uuid.UUID,
    embedder: Embedder,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> int:
    sections = (
        (
            await session.scalars(
                select(Section).where(Section.version_id == version_id).order_by(Section.ordinal)
            )
        )
        .unique()
        .all()
    )
    if not sections:
        raise VersionNotFound(f"version {version_id} has no sections")

    chunks = chunk_sections(
        [
            ParsedSection(
                heading_path=section.heading_path, heading=section.heading, body=section.body
            )
            for section in sections
        ],
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    vectors = await embedder.embed([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError(
            f"{embedder.model} returned {len(vectors)} vectors for {len(chunks)} chunks"
        )

    for chunk, vector in zip(chunks, vectors, strict=True):
        await session.execute(
            insert(Chunk)
            .values(
                version_id=version_id,
                embedding_model=embedder.model,
                ordinal=chunk.ordinal,
                heading_path=chunk.heading_path,
                text=chunk.text,
                token_estimate=chunk.token_estimate,
                embedding=vector,
            )
            .on_conflict_do_nothing(index_elements=["version_id", "embedding_model", "ordinal"])
        )
    await session.flush()
    return len(chunks)
