"""Anthropic Messages API adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from firebrief.llm.errors import ProviderServerError, ProviderTimeout, error_from_status
from firebrief.llm.types import LLMRequest, LLMResponse, Role, Usage

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_BASE_URL = "https://api.anthropic.com"


@dataclass(slots=True)
class AnthropicProvider:
    api_key: str
    client: httpx.AsyncClient
    base_url: str = DEFAULT_BASE_URL
    name: str = "anthropic"

    def payload(self, request: LLMRequest) -> dict[str, object]:
        system = "\n\n".join(m.content for m in request.messages if m.role is Role.SYSTEM)
        messages = [
            {"role": m.role.value, "content": m.content}
            for m in request.messages
            if m.role is not Role.SYSTEM
        ]
        body: dict[str, object] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if system:
            body["system"] = system
        return body

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/messages",
                json=self.payload(request),
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                timeout=request.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"anthropic timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise ProviderTimeout(f"anthropic transport error: {exc}") from exc

        if response.status_code >= 400:
            raise error_from_status(
                response.status_code,
                body=response.text,
                retry_after_s=_retry_after(response),
            )

        try:
            data = response.json()
            text = "".join(
                block["text"] for block in data["content"] if block.get("type") == "text"
            )
            usage = Usage(
                input_tokens=int(data["usage"]["input_tokens"]),
                output_tokens=int(data["usage"]["output_tokens"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderServerError(f"anthropic returned an unexpected payload: {exc}") from exc

        return LLMResponse(
            text=text,
            usage=usage,
            model=str(data.get("model", request.model)),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=str(data.get("stop_reason") or "") or None,
        )


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
