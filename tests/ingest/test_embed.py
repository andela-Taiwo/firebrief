from __future__ import annotations

import json
import math

import httpx
import pytest

from firebrief.ingest.embed import FakeEmbedder, OpenAIEmbedder, validate_vectors


async def test_the_fake_is_deterministic() -> None:
    embedder = FakeEmbedder(dimensions=4)
    first = await embedder.embed(["hello"])
    second = await embedder.embed(["hello"])

    assert first == second
    assert len(first[0]) == 4


async def test_openai_sends_the_key_and_orders_by_index() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = OpenAIEmbedder(api_key="secret", client=client, dimensions=2)
        vectors = await embedder.embed(["first", "second"])

    assert captured["path"] == "/v1/embeddings"
    assert captured["auth"] == "Bearer secret"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["input"] == ["first", "second"]
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_validate_vectors_rejects_a_wrong_count() -> None:
    with pytest.raises(ValueError, match="expected 2 vectors"):
        validate_vectors([[0.1]], expected=2, dimensions=1)


def test_validate_vectors_rejects_a_wrong_dimension() -> None:
    with pytest.raises(ValueError, match="expected 3 dimensions"):
        validate_vectors([[0.1, 0.2]], expected=1, dimensions=3)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_validate_vectors_rejects_non_finite_values(bad: float) -> None:
    with pytest.raises(ValueError, match="NaN or infinity"):
        validate_vectors([[0.1, bad]], expected=1, dimensions=2)
