"""One interface for every model call."""

from firebrief.llm.anthropic import AnthropicProvider
from firebrief.llm.base import Provider
from firebrief.llm.errors import (
    AllProvidersFailed,
    LLMError,
    ProviderAuthenticationError,
    ProviderClientError,
    ProviderRateLimited,
    ProviderServerError,
    ProviderTimeout,
)
from firebrief.llm.fake import FakeProvider
from firebrief.llm.openai import OpenAIProvider
from firebrief.llm.router import Route, Router
from firebrief.llm.types import LLMRequest, LLMResponse, Message, Role, Usage

__all__ = [
    "AllProvidersFailed",
    "AnthropicProvider",
    "FakeProvider",
    "LLMError",
    "LLMRequest",
    "LLMResponse",
    "Message",
    "OpenAIProvider",
    "Provider",
    "ProviderAuthenticationError",
    "ProviderClientError",
    "ProviderRateLimited",
    "ProviderServerError",
    "ProviderTimeout",
    "Role",
    "Route",
    "Router",
    "Usage",
]
