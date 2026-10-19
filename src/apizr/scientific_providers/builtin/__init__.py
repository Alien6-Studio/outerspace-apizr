"""Official source-only recognizers shipped and selected by default in the core."""

from .inputs import discover_inputs
from .metrics import discover_metrics
from .outputs import discover_outputs
from .provider import BuiltinProvider
from .randomness import discover_randomness

__all__ = [
    "BuiltinProvider",
    "discover_inputs",
    "discover_metrics",
    "discover_outputs",
    "discover_randomness",
]
