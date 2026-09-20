"""Static repository inventory; no graph, imports or execution of user code."""

from .discovery import ScanError
from .model import CapabilityEntry, Catalog, Code, Diagnostic, SourceUnit
from .policy import ScanPolicy
from .scanner import scan, scan_sources
from .serialization import catalog_bytes, catalog_digest, policy_bytes, policy_digest

__all__ = [
    "ScanError",
    "CapabilityEntry",
    "Catalog",
    "Code",
    "Diagnostic",
    "SourceUnit",
    "ScanPolicy",
    "scan",
    "scan_sources",
    "catalog_bytes",
    "catalog_digest",
    "policy_bytes",
    "policy_digest",
]
