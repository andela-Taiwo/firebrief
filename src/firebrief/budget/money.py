"""Money is stored as integer micro-units of the billing currency.

One unit (one pound, one dollar) is 1_000_000 micros. No floating point ever
touches an amount that a customer is charged.
"""

from decimal import ROUND_HALF_UP, Decimal

Money = int

MICROS_PER_UNIT = 1_000_000

__all__ = ["MICROS_PER_UNIT", "Money", "ceil_div", "major_to_micros"]


def ceil_div(numerator: int, denominator: int) -> int:
    """Integer ceiling division. Raises on a non-positive denominator."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    return -(-numerator // denominator)


def major_to_micros(amount: Decimal) -> Money:
    """Convert a currency amount (for example 3.00) to integer micros."""
    return int((amount * MICROS_PER_UNIT).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
