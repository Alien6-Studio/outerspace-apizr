"""Forge-neutral static CI operations and their portable result contract."""

from .models import CIResult, Operation
from .runner import CIError, execute

__all__ = ["CIResult", "Operation", "CIError", "execute"]
