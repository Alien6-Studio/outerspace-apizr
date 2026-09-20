from typing import Literal, Union


def calculate(value: int, /, *, mode: Literal["a", "b"] = "a") -> Union[int, str]:
    """Calculate a value using the declared mode."""
    return value


async def describe(value: int | None = None) -> str:
    return str(value)
