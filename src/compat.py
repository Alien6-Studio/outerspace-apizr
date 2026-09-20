"""Compatibility helpers shared by Python 3.8 through 3.14."""

import ast
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    import importlib_metadata as metadata
else:
    from importlib import metadata as metadata

__all__ = [
    "DEFAULT_PYTHON",
    "metadata",
    "is_relative_to",
    "stdlib_module_names",
    "unparse",
]

DEFAULT_PYTHON = sys.version_info[:2]


def is_relative_to(path: Path, parent: Path) -> bool:
    """Path.is_relative_to was introduced in Python 3.9."""
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def stdlib_module_names():
    if hasattr(sys, "stdlib_module_names"):
        return sys.stdlib_module_names
    from stdlib_list import stdlib_list

    return {name.split(".")[0] for name in stdlib_list("{}.{}".format(*DEFAULT_PYTHON))}


def unparse(node):
    if hasattr(ast, "unparse"):
        return ast.unparse(node)
    from astunparse import unparse as ast_unparse

    return ast_unparse(node).strip()
