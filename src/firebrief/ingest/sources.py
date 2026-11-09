"""Where documents come from.

`FakeSource` is what tests use. `GovUkContentApi` reads metadata from the reviewed
manifest and refuses unlisted slugs; it understands both the plain `details.body`
shape and the `details.parts[]` shape that guide-style pages use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape

import httpx

from firebrief.ingest.manifest import Manifest, UnlistedDocument
from firebrief.ingest.types import SourceDocument

USER_AGENT = "firebrief/0.1 (+https://github.com/andela-Taiwo/firebrief)"


def html_from_payload(payload: dict[str, object]) -> str:
    details = payload.get("details") or {}
    if not isinstance(details, dict):
        raise ValueError("content item has no details")

    body = details.get("body")
    if isinstance(body, str) and body.strip():
        return body

    parts = details.get("parts")
    if isinstance(parts, list) and parts:
        chunks: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            title = part.get("title")
            part_body = part.get("body")
            if isinstance(title, str) and title.strip():
                chunks.append(f"<h2>{escape(title)}</h2>")
            if isinstance(part_body, str) and part_body.strip():
                chunks.append(part_body)
        if chunks:
            return "".join(chunks)

    raise ValueError("content item has no body or parts")


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
    manifest: Manifest
    base_url: str = "https://www.gov.uk/api/content"

    async def fetch(self, slug: str) -> SourceDocument:
        meta = self.manifest.get(slug)
        response = await self.client.get(
            f"{self.base_url}/{slug}",
            timeout=30.0,
            headers={"user-agent": USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"{slug}: unexpected payload")

        return SourceDocument(
            slug=slug,
            title=meta.title or str(payload.get("title") or slug),
            source_url=f"https://www.gov.uk/{slug}",
            html=html_from_payload(payload),
            licence=meta.licence,
            edition=meta.edition,
            fetched_at=datetime.now(UTC),
            effective_from=meta.effective_from,
        )


__all__ = ["FakeSource", "GovUkContentApi", "UnlistedDocument", "html_from_payload"]
