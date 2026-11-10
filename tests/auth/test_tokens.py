from __future__ import annotations

import uuid

import pytest

from firebrief.auth.tokens import InvalidToken, hash_token, new_token, tenant_from_token


def test_a_token_carries_its_tenant_and_a_secret() -> None:
    tenant = uuid.uuid4()
    token = new_token(tenant)

    assert tenant_from_token(token) == tenant
    assert len(token.split(".", 1)[1]) >= 20


def test_tokens_are_not_predictable() -> None:
    tenant = uuid.uuid4()

    assert new_token(tenant) != new_token(tenant)


def test_hashing_is_stable_and_not_reversible() -> None:
    token = new_token(uuid.uuid4())

    assert hash_token(token) == hash_token(token)
    assert len(hash_token(token)) == 64
    assert token not in hash_token(token)


@pytest.mark.parametrize(
    "token",
    ["", "not-a-token", "018f0000-0000-7000-8000-000000000001", "018f0000.abc", "abc.short"],
)
def test_malformed_tokens_are_refused(token: str) -> None:
    with pytest.raises(InvalidToken):
        tenant_from_token(token)
