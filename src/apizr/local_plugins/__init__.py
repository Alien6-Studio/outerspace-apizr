"""Explicit installation of local extensions; no discovery or activation."""

from .activation import (
    disable_extension,
    enable_extension,
    read_arguments,
    resolve_active_extension,
    run_extension,
)
from .download import (
    DownloadCancelled,
    DownloadLimits,
    install_from_source,
    install_from_url,
)
from .models import Installation, Inventory, Manifest, PluginError
from .operations import install_extension, list_extensions

__all__ = [
    "DownloadCancelled",
    "DownloadLimits",
    "install_from_source",
    "install_from_url",
    "enable_extension",
    "disable_extension",
    "run_extension",
    "read_arguments",
    "resolve_active_extension",
    "Installation",
    "Inventory",
    "Manifest",
    "PluginError",
    "install_extension",
    "list_extensions",
]
