"""Where documents come from.

`FakeSource` is what tests use. `GovUkContentApi` is the real adapter; it is thin
on purpose, because the interesting work is parsing and versioning, and a fat
network client would be a second thing to test badly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from firebrief.ingest.types import SourceDocument


@dataclass
class FakeSource:
    documents: dict[str, SourceDocument] = field(default_factory=dict)

    async def fetch(self, slug: str) -> SourceDocument:
        try:
            return self.documents[slug]
        except KeyError as exc:
            raise LookupError(f"no fake document for {slug!r}") from exc


@dataclass
class GovUkContentApi:
    """Fetch a GOV.UK content item. Not exercised against the network in tests."""

    client: httpx.AsyncClient
    base_url: str = "https://www.gov.uk/api/content"
    licence: str = "OGL-3.0"

    async def fetch(self, slug: str) -> SourceDocument:
        response = await self.client.get(f"{self.base_url}/{slug}", timeout=30.0)
        response.raise_for_status()
        payload = response.json()
        details = payload.get("details") or {}
        html = str(details.get("body") or "")
        if not html.strip():
            raise ValueError(f"{slug}: the content API returned no body")

        return SourceDocument(
            slug=slug,
            title=str(payload.get("title") or slug),
            source_url=f"https://www.gov.uk/{slug}",
            html=html,
            licence=self.licence,
            edition="unknown",
            fetched_at=datetime.now(UTC),
        )
