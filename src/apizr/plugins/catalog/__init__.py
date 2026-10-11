"""Versioned plugin metadata and explicit preparation for offline project sync."""

from .generation import generate_entries
from .models import Catalog, CatalogError, Entry, Resolution
from .operations import load_catalog, resolve_profile, select_entry, serialize
