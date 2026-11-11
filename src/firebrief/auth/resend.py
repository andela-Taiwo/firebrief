"""Sending sign-in links through Resend.

The link carries the token in the URL fragment, so it never reaches an HTTP access log:
browsers do not send fragments.

A delivery failure raises `EmailDeliveryError`, which the API logs and swallows: the caller
still gets the same 202, because whether an address exists must not be observable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

DEFAULT_BASE_URL = "https://api.resend.com"
DEFAULT_FROM = "Firebrief <onboarding@resend.dev>"
SUBJECT = "Your Firebrief sign-in link"


class EmailDeliveryError(Exception):
    """The provider refused or could not accept the message."""


@dataclass
class ResendSender:
    api_key: str
    web_url: str
    from_address: str = DEFAULT_FROM
    client: httpx.AsyncClient = field(default_factory=httpx.AsyncClient)
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 10.0

    def link(self, token: str) -> str:
        return f"{self.web_url.rstrip('/')}/auth/verify#token={token}"

    def payload(self, *, to: str, token: str) -> dict[str, object]:
        link = self.link(token)
        text = (
            "Use this link to sign in to Firebrief:\n\n"
            f"{link}\n\n"
            "The link expires in 15 minutes and works once. "
            "If you did not ask for it, you can ignore this email."
        )
        html = (
            "<p>Use this link to sign in to Firebrief:</p>"
            f'<p><a href="{link}">Sign in to Firebrief</a></p>'
            "<p>The link expires in 15 minutes and works once. "
            "If you did not ask for it, you can ignore this email.</p>"
        )
        return {
            "from": self.from_address,
            "to": [to],
            "subject": SUBJECT,
            "text": text,
            "html": html,
        }

    async def send_magic_link(self, *, to: str, token: str) -> None:
        try:
            response = await self.client.post(
                f"{self.base_url}/emails",
                headers={"authorization": f"Bearer {self.api_key}"},
                json=self.payload(to=to, token=token),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise EmailDeliveryError(f"resend request failed: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            # The provider's body is included, but never the token or the link.
            raise EmailDeliveryError(
                f"resend rejected the message with status {response.status_code}"
            )
