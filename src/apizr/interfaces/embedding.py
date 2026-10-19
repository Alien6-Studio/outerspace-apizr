"""Closed portable JSON-admission closure for generated standalone transports."""

from importlib.resources import files
from typing import Literal

PORTABLE_ADMISSION_FILES = (
    "apizr_json_preflight.py",
    "apizr_json_budget.py",
    "apizr_http_admission.py",
    "apizr_results.py",
    "apizr_mcp_transport.py",
)


def portable_imports(source: str) -> str:
    for original, portable in (
        ("apizr.contracts.json_budget", "apizr_json_preflight"),
        ("apizr.interfaces.json_budget", "apizr_json_budget"),
        ("apizr.interfaces.http_admission", "apizr_http_admission"),
        ("apizr.interfaces.results", "apizr_results"),
        ("apizr.generators.mcp.transport", "apizr_mcp_transport"),
    ):
        source = source.replace(f"from {original} import", f"from {portable} import")
    return source


def admission_files(transport: Literal["rest", "mcp"]) -> dict[str, bytes]:
    modules = {
        "apizr_json_preflight.py": ("apizr.contracts", "json_budget.py"),
        "apizr_json_budget.py": ("apizr.interfaces", "json_budget.py"),
        "apizr_http_admission.py": ("apizr.interfaces", "http_admission.py"),
        "apizr_results.py": ("apizr.interfaces", "results.py"),
    }
    if transport == "mcp":
        modules["apizr_mcp_transport.py"] = ("apizr.generators.mcp", "transport.py")
    return {
        name: portable_imports(
            files(package).joinpath(path).read_text(encoding="utf-8")
        ).encode("utf-8")
        for name, (package, path) in modules.items()
    }


def inline_admission_source() -> str:
    """Retain the historical single-file REST adapter, using the same sources."""
    return "\n\n".join(
        "\n".join(
            line
            for line in content.decode("utf-8").splitlines()
            if not line.startswith("from apizr_")
        )
        for content in admission_files("rest").values()
    )
