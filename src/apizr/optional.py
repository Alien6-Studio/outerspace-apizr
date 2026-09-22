"""Actionable optional-workflow requirements without automatic installation."""

from importlib.util import find_spec


class MissingExtra(ValueError):
    pass


def available(*modules: str) -> bool:
    return all(find_spec(name) is not None for name in modules)


def require(extra: str, *modules: str) -> None:
    if not available(*modules):
        raise MissingExtra(
            f"This workflow requires the '{extra}' extra. Install "
            f"'outerspace-apizr[{extra}]' matching your Apizr version "
            f"(from a checkout: python -m pip install '.[{extra}]')."
        )
