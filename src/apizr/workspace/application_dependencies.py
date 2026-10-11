"""Capture bounded application-wheel import providers without importing packages."""

import io
import re
import zipfile
from pathlib import Path

from apizr.capabilities.model import Digest
from apizr.contracts.application import dependency_pins
from apizr.contracts.dependencies import DependencyWheel
from apizr.plugins.artifacts.models import PluginError, canonical_name
from apizr.plugins.artifacts.wheel import MAX_WHEEL_BYTES, inspect_dependency_bytes
from apizr.workspace.files import read_regular


def capture_dependency_wheels(
    directory: Path, pins: tuple[str, ...], *, snapshots: dict[str, bytes] | None = None
) -> tuple[DependencyWheel, ...]:
    """Read exactly one wheel for every selected pin; never resolve/download.

    Reuse the shared wheel admission checks (identity, bounded ZIP, path/link/
    customization refusal). Derive modules from actual members, not package-name
    guesses or a caller-provided top_level.txt. Other distribution wheels in a
    prepared closure are not implicitly selected as serving authority.
    """
    pins = dependency_pins(pins)
    entries = []
    for entry in directory.iterdir():
        if len(entries) >= 1024:
            raise ValueError("dependency_wheelhouse_limit")
        entries.append(entry)
    result = []
    total = 0
    for pin in pins:
        name, version = pin.split("==")
        matching = [
            entry
            for entry in entries
            if entry.name.endswith(".whl")
            and len(parts := entry.name[:-4].split("-")) in (5, 6)
            and canonical_name(parts[0]) == name
            and parts[1] == version
        ]
        if len(matching) != 1:
            raise ValueError("dependency_wheel_missing_or_ambiguous")
        path = matching[0]
        raw = read_regular(path, MAX_WHEEL_BYTES)
        total += len(raw)
        if total > 256 * 1024 * 1024:
            raise ValueError("dependency_wheelhouse_limit")
        evidence = inspect_application_wheel(path.name, raw)
        if evidence.pin != pin:
            raise ValueError("dependency_wheel_identity_mismatch")
        result.append(evidence)
        if snapshots is not None:
            snapshots[path.name] = raw
    owners: dict[str, str] = {}
    for wheel in result:
        for module in wheel.modules:
            previous = owners.setdefault(module, wheel.pin)
            if previous != wheel.pin:
                raise ValueError("dependency_wheel_import_collision")
    return tuple(result)


def inspect_application_wheel(filename: str, raw: bytes) -> DependencyWheel:
    """Recompute all import evidence from retained bytes, with no filesystem I/O."""
    try:
        metadata = inspect_dependency_bytes(raw, filename)
    except PluginError:
        raise ValueError("dependency_wheel_invalid") from None
    modules: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.namelist():
            parts = member.split("/")
            if len(parts) > 2 and parts[0].endswith(".data"):
                if parts[1] not in {"purelib", "platlib"}:
                    continue
                parts = parts[2:]
            leaf = parts[-1]
            if leaf.endswith(".py"):
                stem = leaf[:-3]
            elif leaf.endswith((".so", ".pyd")):
                stem = leaf.split(".", 1)[0]
            else:
                continue
            names = parts[:-1] + ([] if stem == "__init__" else [stem])
            if not names or any(
                not re.fullmatch(r"[A-Za-z_]\w*", part, re.ASCII) for part in names
            ):
                continue
            # Include namespace ancestors supplied by actual member files.
            modules.update(".".join(names[:end]) for end in range(1, len(names) + 1))
    return DependencyWheel(
        pin=f"{metadata.name}=={metadata.version}",
        filename=filename,
        digest=Digest.of_bytes(raw),
        modules=tuple(modules),
    )
