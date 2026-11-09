"""Split sections into chunks small enough for a retrieval context.

A section is the unit a citation points at, so a chunk records the section it came
from and its character range inside that section's body. `heading_path` alone is
not enough: a document can have two sections called "Notes".

A section that fits the budget stays whole; a longer one is split on word
boundaries with overlap, and every piece keeps the heading path.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from firebrief.budget.estimate import estimate_tokens
from firebrief.ingest.types import ParsedSection

DEFAULT_MAX_TOKENS = 300
DEFAULT_OVERLAP_TOKENS = 50

WORD = re.compile(r"\S+")


def chunker_id(max_tokens: int, overlap_tokens: int) -> str:
    """Identity of the chunking configuration.

    Part of the chunk key, so changing the budget or the algorithm produces a new,
    complete set instead of mixing old and new ordinals.
    """
    return f"words-v1:{max_tokens}/{overlap_tokens}"


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    section_index: int
    heading_path: str
    text: str
    token_estimate: int
    char_start: int
    char_end: int


def _spans(body: str, max_tokens: int, overlap_tokens: int) -> list[tuple[int, int]]:
    words = [(match.start(), match.end()) for match in WORD.finditer(body)]
    if not words:
        return []

    spans: list[tuple[int, int]] = []
    start = 0
    total = len(words)
    while start < total:
        end = start
        while end < total:
            chars = words[end][1] - words[start][0]
            if math.ceil(chars / 3) > max_tokens and end > start:
                break
            end += 1
        spans.append((words[start][0], words[end - 1][1]))
        if end >= total:
            break
        overlap_words = max(1, overlap_tokens // 2)
        start = max(start + 1, end - overlap_words)
    return spans


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
    for section_index, section in enumerate(sections):
        for start, end in _spans(section.body, max_tokens, overlap_tokens):
            text = section.body[start:end]
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    section_index=section_index,
                    heading_path=section.heading_path,
                    text=text,
                    token_estimate=estimate_tokens(text),
                    char_start=start,
                    char_end=end,
                )
            )
    return chunks
