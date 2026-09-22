"""Public API and a currently ineligible relative-import example."""


def run(quantity: int = 2, /, *, fee: int = 1) -> int:
    """Compute a quote using an unexposed cross-module helper."""
    return helper(quantity) + fee


def helper(quantity: int) -> int:
    from .pricing import calculate

    return calculate(quantity)


async def quote(quantity: int) -> int:
    """Readiness v1 refuses this local import; it is deliberately unselected."""
    from .pricing import run

    return await run(quantity)
