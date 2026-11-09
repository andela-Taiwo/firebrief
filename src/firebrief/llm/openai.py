"""OpenAI Chat Completions adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from firebrief.llm.errors import ProviderServerError, ProviderTimeout, error_from_status
from firebrief.llm.types import LLMRequest, LLMResponse, Usage

DEFAULT_BASE_URL = "https://api.openai.com"


@dataclass(slots=True)
class OpenAIProvider:
    api_key: str
    client: httpx.AsyncClient
    base_url: str = DEFAULT_BASE_URL
    name: str = "openai"

    def payload(self, request: LLMRequest) -> dict[str, object]:
        return {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
        }

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = time.perf_counter()
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json=self.payload(request),
                headers={
                    "authorization": f"Bearer {self.api_key}",
                    "content-type": "application/json",
                },
                timeout=request.timeout_s,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout(f"openai timed out: {exc}") from exc
        except httpx.TransportError as exc:
            raise ProviderTimeout(f"openai transport error: {exc}") from exc

        if response.status_code >= 400:
            raise error_from_status(
                response.status_code,
                body=response.text,
                retry_after_s=_retry_after(response),
            )

        try:
            data = response.json()
            text = str(data["choices"][0]["message"]["content"])
            usage = Usage(
                input_tokens=int(data["usage"]["prompt_tokens"]),
                output_tokens=int(data["usage"]["completion_tokens"]),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderServerError(f"openai returned an unexpected payload: {exc}") from exc

        return LLMResponse(
            text=text,
            usage=usage,
            model=str(data.get("model", request.model)),
            provider=self.name,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None
