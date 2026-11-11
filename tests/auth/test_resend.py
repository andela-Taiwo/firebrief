from __future__ import annotations

import httpx
import pytest

from firebrief.auth.resend import EmailDeliveryError, ResendSender

TOKEN = "018f0000-0000-7000-8000-0000000000aa.secret-value"


def sender(handler) -> ResendSender:  # type: ignore[no-untyped-def]
    return ResendSender(
        api_key="re_test_key",
        web_url="http://127.0.0.1:5173",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_the_link_carries_the_token_in_the_fragment() -> None:
    link = sender(lambda request: httpx.Response(200)).link(TOKEN)

    assert link == f"http://127.0.0.1:5173/auth/verify#token={TOKEN}"
    assert "?" not in link, "a query string would reach the server's access log"


async def test_the_message_is_sent_through_resend() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"id": "email_1"})

    await sender(handler).send_magic_link(to="dev@firebrief.local", token=TOKEN)

    request = captured[0]
    body = request.read().decode()
    assert request.url == "https://api.resend.com/emails"
    assert request.headers["authorization"] == "Bearer re_test_key"
    assert '"to":["dev@firebrief.local"]' in body.replace(" ", "")
    assert "Your Firebrief sign-in link" in body
    assert f"#token={TOKEN}" in body
    assert "15 minutes" in body


async def test_a_rejected_message_raises_without_leaking_the_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid api key"})

    with pytest.raises(EmailDeliveryError) as caught:
        await sender(handler).send_magic_link(to="dev@firebrief.local", token=TOKEN)

    assert TOKEN not in str(caught.value)
    assert "401" in str(caught.value)


async def test_a_network_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(EmailDeliveryError, match="ConnectError"):
        await sender(handler).send_magic_link(to="dev@firebrief.local", token=TOKEN)
