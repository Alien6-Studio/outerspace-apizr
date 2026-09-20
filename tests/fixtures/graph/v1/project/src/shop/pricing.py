def discount(value: int) -> int:
    return value - 1


def calculate(value: int) -> int:
    return discount(value)


def factorial(n: int) -> int:
    if n > 1:
        return n * factorial(n - 1)
    return 1
