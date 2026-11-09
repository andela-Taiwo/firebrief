"""The reviewed list of documents the corpus may contain.

Licence and edition come from here, not from the fetcher: a page cannot declare
itself Open Government Licence. An unlisted slug is refused.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path


class UnlistedDocument(Exception):
    """The slug is not in the reviewed manifest."""


@dataclass(frozen=True, slots=True)
class SourceMeta:
    slug: str
    title: str
    licence: str
    edition: str
    effective_from: date | None = None


class Manifest:
    def __init__(self, entries: dict[str, SourceMeta]) -> None:
        self._entries = dict(entries)

    @classmethod
    def from_toml(cls, path: Path) -> Manifest:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        documents = data.get("documents") or {}
        entries: dict[str, SourceMeta] = {}
        for slug, raw in documents.items():
            try:
                entries[slug] = SourceMeta(
                    slug=slug,
                    title=str(raw["title"]),
                    licence=str(raw["licence"]),
                    edition=str(raw["edition"]),
                    effective_from=raw.get("effective_from"),
                )
            except KeyError as exc:
                raise ValueError(f"{slug}: manifest entry is missing {exc.args[0]!r}") from exc
        if not entries:
            raise ValueError(f"{path}: the manifest lists no documents")
        return cls(entries)

    def get(self, slug: str) -> SourceMeta:
        try:
            return self._entries[slug]
        except KeyError as exc:
            raise UnlistedDocument(
                f"{slug!r} is not in the reviewed manifest; add it deliberately"
            ) from exc

    def slugs(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)
