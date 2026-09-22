"""Pricing exposes the same bare name as API without a public-name collision."""


async def run(quantity: int, *, unit_price: int = 10) -> int:
    """Calculate the price."""
    return quantity * unit_price


def calculate(quantity: int) -> int:
    """Support code, deliberately not public."""
    return quantity * 10
