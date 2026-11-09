"""Split sections into chunks small enough for a retrieval context.

A section is already the unit a citation points at, so it is the starting point.
A section that fits the budget stays whole; a longer one is split on word
boundaries with overlap, and every piece keeps the heading path so a retrieved
chunk can still say where it came from.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from firebrief.budget.estimate import estimate_tokens
from firebrief.ingest.types import ParsedSection

DEFAULT_MAX_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 50


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    heading_path: str
    text: str
    token_estimate: int


def _split(body: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    words = body.split()
    if not words:
        return []

    pieces: list[str] = []
    start = 0
    while start < len(words):
        end = start
        while end < len(words) and estimate_tokens(" ".join(words[start : end + 1])) <= max_tokens:
            end += 1
        if end == start:  # a single word longer than the budget
            end = start + 1
        pieces.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        overlap_words = max(1, overlap_tokens // 2)
        start = max(start + 1, end - overlap_words)
    return pieces


def chunk_sections(
    sections: Sequence[ParsedSection],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    chunks: list[Chunk] = []
    for section in sections:
        for piece in _split(section.body, max_tokens=max_tokens, overlap_tokens=overlap_tokens):
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    heading_path=section.heading_path,
                    text=piece,
                    token_estimate=estimate_tokens(piece),
                )
            )
    return chunks
