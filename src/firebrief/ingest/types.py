"""The shapes that cross the ingestion boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """What a source returns: bytes plus the metadata a person has reviewed."""

    slug: str
    title: str
    source_url: str
    html: str
    licence: str
    edition: str
    fetched_at: datetime
    effective_from: date | None = None
    effective_to: date | None = None

    def __post_init__(self) -> None:
        if not self.slug.strip():
            raise ValueError("slug must not be empty")
        if not self.html.strip():
            raise ValueError(f"{self.slug}: empty document")


@dataclass(frozen=True, slots=True)
class ParsedSection:
    heading_path: str
    heading: str
    body: str


class DocumentSource(Protocol):
    async def fetch(self, slug: str) -> SourceDocument: ...
