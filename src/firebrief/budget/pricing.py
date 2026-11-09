"""Model prices, loaded from TOML and held as integer micros per million tokens.

Prices are quoted in the billing currency per million tokens (the way providers
publish them). Storing micros per *million* tokens keeps sub-micro prices exact:
0.15 per million tokens becomes 150_000 micros per million tokens, and the
division happens once, with a ceiling, per request.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from firebrief.budget.money import Money, ceil_div, major_to_micros

TOKENS_PER_MTOK = 1_000_000


class PricingError(Exception):
    """Base class for pricing configuration errors."""


class UnknownModelError(PricingError):
    """Raised when a model has no price entry."""


class InvalidPricingError(PricingError):
    """Raised when a price table is malformed."""


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_micros_per_mtok: Money
    output_micros_per_mtok: Money

    def cost(self, input_tokens: int, output_tokens: int) -> Money:
        """Worst-case or exact cost, rounded up once, in micros."""
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must not be negative")
        micros = (
            input_tokens * self.input_micros_per_mtok + output_tokens * self.output_micros_per_mtok
        )
        return ceil_div(micros, TOKENS_PER_MTOK)

    def worst_case(self, prompt_tokens: int, max_output_tokens: int) -> Money:
        return self.cost(prompt_tokens, max_output_tokens)


@dataclass(frozen=True, slots=True)
class PriceTable:
    currency: str
    models: dict[str, ModelPrice]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PriceTable:
        currency = data.get("currency", {}).get("code", "GBP")
        if not isinstance(currency, str) or len(currency) != 3:
            raise InvalidPricingError(f"invalid currency code: {currency!r}")
        raw_models = data.get("models")
        if not isinstance(raw_models, dict) or not raw_models:
            raise InvalidPricingError("pricing table must define at least one model")
        models: dict[str, ModelPrice] = {}
        for name, raw in raw_models.items():
            if not isinstance(raw, dict):
                raise InvalidPricingError(f"model {name!r} must be a table")
            try:
                input_price = Decimal(str(raw["input"]))
                output_price = Decimal(str(raw["output"]))
            except KeyError as exc:
                raise InvalidPricingError(f"model {name!r} is missing {exc.args[0]!r}") from exc
            except (ArithmeticError, ValueError) as exc:
                raise InvalidPricingError(f"model {name!r} has a non-numeric price") from exc
            if input_price < 0 or output_price < 0:
                raise InvalidPricingError(f"model {name!r} has a negative price")
            models[name] = ModelPrice(
                input_micros_per_mtok=major_to_micros(input_price),
                output_micros_per_mtok=major_to_micros(output_price),
            )
        return cls(currency=currency, models=models)

    @classmethod
    def from_toml(cls, path: Path) -> PriceTable:
        with path.open("rb") as handle:
            return cls.from_dict(tomllib.load(handle))

    def price(self, model: str) -> ModelPrice:
        try:
            return self.models[model]
        except KeyError as exc:
            raise UnknownModelError(f"no price configured for model {model!r}") from exc
