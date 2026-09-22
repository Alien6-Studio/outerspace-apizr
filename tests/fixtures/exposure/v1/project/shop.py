from typing import Any


def calculate(value: int) -> int:
    return helper(value)


def helper(value: int) -> int:
    return value + 1


def availability(value: int) -> bool:
    return value > 0


def uncertain() -> int:
    __import__('external_package')
    return 1


def unsupported():
    yield 1
