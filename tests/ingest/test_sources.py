from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from firebrief.ingest.manifest import Manifest, UnlistedDocument
from firebrief.ingest.sources import USER_AGENT, GovUkContentApi, html_from_payload

MANIFEST = Manifest.from_toml(Path("corpus/sources.toml"))


def test_a_plain_body_is_used() -> None:
    html = html_from_payload({"details": {"body": "<p>Body.</p>"}})
    assert html == "<p>Body.</p>"


def test_parts_are_joined_with_their_titles() -> None:
    html = html_from_payload(
        {
            "details": {
                "parts": [
                    {"title": "Part one", "body": "<p>First.</p>"},
                    {"title": "Part two", "body": "<p>Second.</p>"},
                ]
            }
        }
    )

    assert "<h2>Part one</h2><p>First.</p>" in html
    assert "<h2>Part two</h2><p>Second.</p>" in html


def test_a_content_item_with_no_body_or_parts_is_refused() -> None:
    with pytest.raises(ValueError):
        html_from_payload({"details": {}})


async def test_metadata_comes_from_the_manifest_not_the_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == USER_AGENT
        return httpx.Response(
            200,
            json={
                "title": "Ignored page title",
                "details": {"body": "<p>Body.</p>"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GovUkContentApi(client=client, manifest=MANIFEST)
        document = await adapter.fetch("fire-safety-purpose-built-flats")

    assert document.licence == "OGL-3.0"
    assert document.edition == "2019"
    assert document.title == "Fire safety in purpose-built flats"


async def test_an_unlisted_slug_never_reaches_the_network() -> None:
    async with httpx.AsyncClient() as client:
        adapter = GovUkContentApi(client=client, manifest=MANIFEST)
        with pytest.raises(UnlistedDocument):
            await adapter.fetch("not-listed")
