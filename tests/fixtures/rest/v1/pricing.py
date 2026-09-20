from typing import Literal


def total(
    prices: list[int | float],
    /,
    currency: Literal["EUR", "USD"] = "EUR",
    *,
    tax: float = 0.2,
) -> float:
    """Return the total with tax; currency is a declared request choice."""
    return sum(prices) * (1 + tax)


async def greet(name: str = "world", *, punctuation: str = "!") -> str:
    """Return a greeting."""
    return f"Hello {name}{punctuation}"
