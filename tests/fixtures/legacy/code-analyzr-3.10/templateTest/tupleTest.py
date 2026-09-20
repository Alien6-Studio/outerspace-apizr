from typing import Tuple


def foo(a: tuple, b: (int, float), c: Tuple, d: Tuple[str, int]):
    pass


def bar(a: ((int, str, float), (str, (int, float)))):
    pass


def baz(a: Tuple[Tuple[int, str], Tuple]):
    pass
