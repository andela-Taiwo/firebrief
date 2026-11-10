"""What retrieval returns: evidence, not an answer."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Retrieved:
    chunk_id: uuid.UUID
    section_id: uuid.UUID
    version_id: uuid.UUID
    heading_path: str
    text: str
    score: float
    vector_rank: int | None
    text_rank: int | None
