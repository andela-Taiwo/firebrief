from __future__ import annotations

import json

import httpx
import pytest

from firebrief.llm.anthropic import AnthropicProvider
from firebrief.llm.errors import (
    ProviderClientError,
    ProviderRateLimited,
    ProviderServerError,
    ProviderTimeout,
)
from firebrief.llm.openai import OpenAIProvider
from firebrief.llm.types import LLMRequest, Message, Role


def request_for(model: str = "test-model") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=(Message(Role.SYSTEM, "You are a careful assistant."), Message(Role.USER, "Hi")),
        max_tokens=64,
        temperature=0.0,
    )


async def test_anthropic_maps_request_and_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["api_key"] = request.headers["x-api-key"]
        captured["version"] = request.headers["anthropic-version"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "claude-test",
                "content": [
                    {"type": "thinking", "thinking": "ignored"},
                    {"type": "text", "text": "Cited answer."},
                ],
                "usage": {"input_tokens": 12, "output_tokens": 3},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = AnthropicProvider(api_key="secret", client=client)
        response = await provider.complete(request_for())

    assert captured["path"] == "/v1/messages"
    assert captured["api_key"] == "secret"
    assert captured["version"] == "2023-06-01"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["system"] == "You are a careful assistant."
    assert body["messages"] == [{"role": "user", "content": "Hi"}]
    assert body["max_tokens"] == 64

    assert response.text == "Cited answer."
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 3
    assert response.provider == "anthropic"
    assert response.model == "claude-test"


async def test_openai_maps_request_and_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers["authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "gpt-test",
                "choices": [{"message": {"content": "Cited answer."}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = OpenAIProvider(api_key="secret", client=client)
        response = await provider.complete(request_for())

    assert captured["path"] == "/v1/chat/completions"
    assert captured["auth"] == "Bearer secret"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["messages"][0] == {"role": "system", "content": "You are a careful assistant."}
    assert response.usage.input_tokens == 20
    assert response.usage.output_tokens == 5
    assert response.provider == "openai"


@pytest.mark.parametrize(
    ("status", "expected", "retryable"),
    [
        (429, ProviderRateLimited, True),
        (500, ProviderServerError, True),
        (503, ProviderServerError, True),
        (400, ProviderClientError, False),
    ],
)
async def test_http_status_is_classified(status: int, expected, retryable: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="nope", headers={"retry-after": "2"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIProvider(api_key="secret", client=client)
        with pytest.raises(expected) as raised:
            await provider.complete(request_for())

    assert raised.value.retryable is retryable
    assert raised.value.status == status
    if status == 429:
        assert raised.value.retry_after_s == 2.0


async def test_transport_failure_is_retryable_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = AnthropicProvider(api_key="secret", client=client)
        with pytest.raises(ProviderTimeout) as raised:
            await provider.complete(request_for())

    assert raised.value.retryable is True


def test_request_validation() -> None:
    with pytest.raises(ValueError):
        LLMRequest(model="m", messages=())
    with pytest.raises(ValueError):
        LLMRequest(model="m", messages=(Message(Role.USER, "hi"),), max_tokens=0)
    with pytest.raises(ValueError):
        LLMRequest(model="m", messages=(Message(Role.USER, "hi"),), temperature=3.0)
