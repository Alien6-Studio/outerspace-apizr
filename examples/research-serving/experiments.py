from contextlib import contextmanager


@contextmanager
def trial():
    yield 1
