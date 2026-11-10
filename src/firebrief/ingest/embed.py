"""Embedding models behind one interface.

The fake is deterministic and offline, so tests and local runs cost nothing. The
real adapter takes its key explicitly and sends it, like the LLM adapters do.
"""

from __future__ import annotations

import hashlib
import math
import re
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
            vectors.append(
                [(digest[index % len(digest)] / 127.5) - 1.0 for index in range(self.dimensions)]
            )
        return vectors


@dataclass
class OpenAIEmbedder:
    """OpenAI embeddings. Not exercised against the network in tests."""

    api_key: str
    client: httpx.AsyncClient
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    base_url: str = "https://api.openai.com"

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self.client.post(
            f"{self.base_url}/v1/embeddings",
            json={"model": self.model, "input": list(texts)},
            headers={"authorization": f"Bearer {self.api_key}"},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload["data"], key=lambda item: item["index"])
        return [[float(value) for value in item["embedding"]] for item in data]


def validate_vectors(vectors: Sequence[Sequence[float]], *, expected: int, dimensions: int) -> None:
    if len(vectors) != expected:
        raise ValueError(f"expected {expected} vectors, got {len(vectors)}")
    for vector in vectors:
        if len(vector) != dimensions:
            raise ValueError(f"expected {dimensions} dimensions, got {len(vector)}")
        if any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding contains NaN or infinity")


@dataclass(frozen=True)
class BagOfWordsEmbedder:
    """Hashed bag of words: deterministic, offline, and meaningful for ranking.

    The hash-based fake is fine for storage tests, but two different texts are no
    more similar than two random vectors. This one at least shares buckets with the
    query, so retrieval tests can assert an ordering.
    """

    model: str = "bow-256"
    dimensions: int = 1024

    def _bucket(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") % self.dimensions

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                vector[self._bucket(token)] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors
