# # Pricing API
# A small, deterministic example with no external data.


from typing import Dict, List


def total(prices: List[float], tax: float = 0.2) -> float:
    return round(sum(prices) * (1 + tax), 2)


async def greet(name: str = "world") -> Dict[str, str]:
    return {"message": f"Hello {name}!"}
