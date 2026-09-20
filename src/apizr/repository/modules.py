"""Lexical identities, independent of package importability."""

from pathlib import PurePosixPath

from apizr.capabilities.types import logical_module

from .policy import ScanPolicy, relative_path


def source_root(path: str, policy: ScanPolicy) -> str | None:
    path = relative_path(path)
    for root in policy.source_roots:
        if root == "." or path.startswith(root + "/"):
            relative = PurePosixPath(path).relative_to(root)
            if any(part in policy.excluded_directories for part in relative.parts[:-1]):
                return None
            if relative.suffix in policy.included_suffixes:
                return root
    return None


def module_name(path: str, root: str) -> str:
    relative = PurePosixPath(relative_path(path)).relative_to(
        relative_path(root, allow_root=True)
    )
    parts = list(relative.parts)
    if relative.name == "__init__.py":
        parts.pop()
    else:
        parts[-1] = relative.stem
    if not parts or any("." in logical_module(part) for part in parts):
        raise ValueError("Source path does not identify a logical Python module")
    return logical_module(".".join(parts))
