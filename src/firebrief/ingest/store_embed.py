"""Chunk and embed a stored version.

Idempotent: re-running adds nothing, and the result says how many chunks were
written versus already present. Additive: a different model or a different
chunking configuration produces a complete second set, and the first stays intact.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from firebrief.db.models import Chunk, Section
from firebrief.ingest.chunk import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    chunk_sections,
    chunker_id,
)
from firebrief.ingest.embed import Embedder, validate_vectors
from firebrief.ingest.types import ParsedSection

EMBED_BATCH = 64


class VersionNotFound(Exception):
    """No such version, or it has no sections."""


@dataclass(frozen=True, slots=True)
class EmbedResult:
    version_id: uuid.UUID
    created: int
    existing: int

    @property
    def total(self) -> int:
        return self.created + self.existing


async def _embed_all(embedder: Embedder, texts: Sequence[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors.extend(await embedder.embed(texts[start : start + EMBED_BATCH]))
    return vectors


async def embed_version(
    session: AsyncSession,
    version_id: uuid.UUID,
    embedder: Embedder,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> EmbedResult:
    sections = (
        await session.scalars(
            select(Section).where(Section.version_id == version_id).order_by(Section.ordinal)
        )
    ).all()
    if not sections:
        raise VersionNotFound(f"version {version_id} has no sections")

    chunks = chunk_sections(
        [
            ParsedSection(heading_path=s.heading_path, heading=s.heading, body=s.body)
            for s in sections
        ],
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )

    # Embed the heading path with the text: a chunk about fire doors may never say
    # "fire doors" in its body, and the fingerprint is what makes it findable.
    vectors = await _embed_all(embedder, [f"{c.heading_path}\n\n{c.text}" for c in chunks])
    validate_vectors(vectors, expected=len(chunks), dimensions=embedder.dimensions)

    configuration = chunker_id(max_tokens, overlap_tokens)
    rows = [
        {
            "version_id": version_id,
            "section_id": sections[chunk.section_index].id,
            "embedding_model": embedder.model,
            "chunker": configuration,
            "ordinal": chunk.ordinal,
            "heading_path": chunk.heading_path,
            "text": chunk.text,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "token_estimate": chunk.token_estimate,
            "dimensions": embedder.dimensions,
            "embedding": vector,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

    inserted = 0
    if rows:
        result = await session.execute(
            insert(Chunk)
            .values(rows)
            .on_conflict_do_nothing(
                index_elements=["version_id", "embedding_model", "chunker", "ordinal"]
            )
            .returning(Chunk.id)
        )
        inserted = len(result.scalars().all())

    return EmbedResult(version_id=version_id, created=inserted, existing=len(rows) - inserted)
