"""Explicit installation of local extensions; no discovery or activation."""

from .models import Installation, Inventory, Manifest, PluginError
from .operations import install_extension, list_extensions

__all__ = [
    "Installation",
    "Inventory",
    "Manifest",
    "PluginError",
    "install_extension",
    "list_extensions",
]
