"""Provider errors, classified as retryable or not.

Retrying a request that failed for a reason that will not change (a 400, a 401)
makes an outage worse and costs money, so classification happens at the adapter
boundary and the router trusts it.
"""

from __future__ import annotations


class LLMError(Exception):
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after_s = retry_after_s


class ProviderTimeout(LLMError):
    retryable = True


class ProviderRateLimited(LLMError):
    retryable = True


class ProviderServerError(LLMError):
    retryable = True


class ProviderClientError(LLMError):
    retryable = False


class ProviderAuthenticationError(LLMError):
    retryable = False


class AllProvidersFailed(LLMError):
    """Every route and retry was exhausted. Carries the last error."""

    retryable = False

    def __init__(self, message: str, last_error: LLMError | None = None) -> None:
        super().__init__(message)
        self.last_error = last_error


def error_from_status(
    status: int, *, body: str = "", retry_after_s: float | None = None
) -> LLMError:
    snippet = body[:200]
    if status in (401, 403):
        return ProviderAuthenticationError(
            f"provider rejected the credentials ({status}): {snippet}", status=status
        )
    if status == 429:
        return ProviderRateLimited(
            f"provider rate limited ({status})", status=status, retry_after_s=retry_after_s
        )
    if status in (408, 409) or status >= 500:
        return ProviderServerError(
            f"provider error ({status}): {snippet}", status=status, retry_after_s=retry_after_s
        )
    return ProviderClientError(
        f"provider rejected the request ({status}): {snippet}", status=status
    )
