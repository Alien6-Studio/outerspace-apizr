"""Typed, static Capability IR v1; independent of legacy generation."""

from .analyzer import inspect_file, inspect_source
from .model import CapabilityDocument
from .serialization import canonical_bytes, document_digest

__all__ = [
    "CapabilityDocument",
    "canonical_bytes",
    "document_digest",
    "inspect_file",
    "inspect_source",
]
