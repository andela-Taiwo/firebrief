"""Embedding models behind one interface.

The fake is deterministic and offline, so tests and local runs cost nothing. The
real adapter is thin: the interesting work is chunking and versioning.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class FakeEmbedder:
    """Deterministic vectors derived from the text: same input, same output."""

    model: str = "fake-embed-1"
    dimensions: int = 8

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            values = [
                (digest[index % len(digest)] / 127.5) - 1.0 for index in range(self.dimensions)
            ]
            vectors.append(values)
        return vectors


@dataclass
class OpenAIEmbedder:
    """OpenAI embeddings. Not exercised against the network in tests."""

    client: httpx.AsyncClient
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    base_url: str = "https://api.openai.com"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self.client.post(
            f"{self.base_url}/v1/embeddings",
            json={"model": self.model, "input": list(texts)},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload["data"], key=lambda item: item["index"])
        return [[float(value) for value in item["embedding"]] for item in data]
