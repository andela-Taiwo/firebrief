from __future__ import annotations

from decimal import Decimal

import pytest

from firebrief.budget.money import ceil_div, major_to_micros
from firebrief.budget.pricing import (
    InvalidPricingError,
    ModelPrice,
    PriceTable,
    UnknownModelError,
)


def test_major_to_micros_is_exact() -> None:
    assert major_to_micros(Decimal("3.00")) == 3_000_000
    assert major_to_micros(Decimal("0.15")) == 150_000


def test_ceil_div() -> None:
    assert ceil_div(0, 3) == 0
    assert ceil_div(1, 3) == 1
    assert ceil_div(9, 3) == 3
    with pytest.raises(ValueError):
        ceil_div(1, 0)


def test_sub_micro_price_rounds_up_per_request_not_to_zero() -> None:
    # 0.15 per million tokens is 150_000 micros per million tokens.
    price = ModelPrice(input_micros_per_mtok=150_000, output_micros_per_mtok=600_000)
    assert price.cost(1, 0) == 1
    assert price.cost(7, 0) == 2  # 1.05 micros, rounded up
    assert price.cost(0, 0) == 0


def test_worst_case_uses_max_output_tokens() -> None:
    price = ModelPrice(1_000_000, 2_000_000)
    assert price.worst_case(prompt_tokens=100, max_output_tokens=50) == 200


def test_price_table_from_dict() -> None:
    table = PriceTable.from_dict(
        {"currency": {"code": "GBP"}, "models": {"tiny": {"input": 1.0, "output": 2.0}}}
    )
    assert table.currency == "GBP"
    assert table.price("tiny") == ModelPrice(1_000_000, 2_000_000)
    with pytest.raises(UnknownModelError):
        table.price("unknown")


def test_price_table_rejects_malformed_input() -> None:
    with pytest.raises(InvalidPricingError):
        PriceTable.from_dict({"models": {}})
    with pytest.raises(InvalidPricingError):
        PriceTable.from_dict({"models": {"tiny": {"input": 1.0}}})
    with pytest.raises(InvalidPricingError):
        PriceTable.from_dict({"models": {"tiny": {"input": -1.0, "output": 1.0}}})


def test_configured_pricing_file_loads() -> None:
    from pathlib import Path

    table = PriceTable.from_toml(Path("config/pricing.toml"))
    assert table.currency == "GBP"
    assert table.price("claude-sonnet-4-5-20250929").output_micros_per_mtok == 15_000_000
