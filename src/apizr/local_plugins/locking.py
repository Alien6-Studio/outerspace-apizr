"""A bounded requirements subset and private wheel snapshots, not a resolver."""

import hashlib
import io
import os
import re
import stat
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import Parser
from pathlib import Path

from .models import LockedDistribution, Manifest, PluginError, canonical_name
from .wheel import MAX_METADATA_BYTES, inspect_dependency

MAX_LOCK_BYTES = 65536
MAX_WHEELS = 128
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_TOTAL_EXPANDED_BYTES = 512 * 1024 * 1024
LINE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_]{0,127})"
    r"\s+--hash=sha256:([0-9a-fA-F]{64})"
)


@dataclass(frozen=True)
class Lock:
    sha256: str
    packages: tuple[LockedDistribution, ...]


def check_options(requirements: Path | None, wheelhouse: Path | None) -> None:
    if (requirements is None) != (wheelhouse is None):
        raise PluginError("requirements_and_wheelhouse_required")


def read_lock(path: Path) -> Lock:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise PluginError("invalid_requirements_lock")
            raw = source.read(MAX_LOCK_BYTES + 1)
        if len(raw) > MAX_LOCK_BYTES:
            raise PluginError("requirements_lock_too_large")
        # uv-style comments and backslash line continuations, but no options,
        # markers, extras, URLs, paths, wildcard pins or nested requirements.
        logical = re.sub(r"\\\r?\n", " ", raw.decode("utf-8"))
        packages: dict[str, LockedDistribution] = {}
        for line in logical.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            match = LINE.fullmatch(line)
            if match is None:
                raise PluginError("invalid_requirements_lock")
            name, version, digest = match.groups()
            name = canonical_name(name)
            if name in packages:
                raise PluginError("duplicate_locked_distribution")
            packages[name] = LockedDistribution(
                name=name, version=version, sha256=digest.lower()
            )
            if len(packages) > MAX_WHEELS:
                raise PluginError("too_many_locked_wheels")
        if not packages:
            raise PluginError("invalid_requirements_lock")
        return Lock(
            hashlib.sha256(raw).hexdigest(),
            tuple(packages[key] for key in sorted(packages)),
        )
    except (OSError, ValueError):
        raise PluginError("invalid_requirements_lock") from None


def expanded_size(data: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return sum(entry.file_size for entry in archive.infolist())


def prepare(
    lock: Lock,
    wheelhouse: Path,
    manifest: Manifest,
    digest: str,
    data: bytes,
    filename: str,
    work: Path,
) -> list[LockedDistribution]:
    """Only these validated bytes become visible to uv; originals may change."""
    primary = LockedDistribution(
        name=manifest.name, version=manifest.version, sha256=digest.lower()
    )
    if primary not in lock.packages:
        raise PluginError("plugin_lock_mismatch")
    needed = {item.name: item for item in lock.packages if item.name != primary.name}
    found: set[str] = set()
    total = len(data)
    expanded = expanded_size(data)
    snapshot = work / "wheels"
    snapshot.mkdir(mode=0o700)
    (snapshot / filename).write_bytes(data)
    # Bound directory traversal as well as compressed bytes. Reject ambiguous
    # candidates rather than implementing platform/tag selection ourselves.
    count = 0
    with os.scandir(wheelhouse) as entries:
        for entry in entries:
            count += 1
            if count > MAX_WHEELS:
                raise PluginError("too_many_locked_wheels")
            if not entry.name.endswith(".whl"):
                continue  # Never offer non-wheel files (including sdists) to uv.
            if not entry.is_file(follow_symlinks=False):
                raise PluginError("local_wheel_required")
            try:
                name = canonical_name(entry.name.split("-", 1)[0])
            except ValueError:
                raise PluginError("invalid_wheel") from None
            if name == primary.name:
                # Main source is explicit; do not trust a second wheelhouse copy.
                continue
            if name not in needed:
                raise PluginError("unlocked_wheel")
            if name in found:
                raise PluginError("ambiguous_locked_wheel")
            expected = needed[name]
            if total + entry.stat(follow_symlinks=False).st_size > MAX_TOTAL_BYTES:
                raise PluginError("wheelhouse_too_large")
            payload, actual = inspect_dependency(Path(entry.path), expected.sha256)
            total += len(payload)
            expanded += expanded_size(payload)
            if total > MAX_TOTAL_BYTES or expanded > MAX_TOTAL_EXPANDED_BYTES:
                raise PluginError("wheelhouse_too_large")
            if actual != expected:
                raise PluginError("dependency_lock_mismatch")
            (snapshot / entry.name).write_bytes(payload)
            found.add(name)
    if found != set(needed):
        raise PluginError("missing_locked_wheel")
    if total > MAX_TOTAL_BYTES or expanded > MAX_TOTAL_EXPANDED_BYTES:
        raise PluginError("wheelhouse_too_large")
    (work / "requirements.txt").write_text(
        "".join(
            f"{item.name}=={item.version} --hash=sha256:{item.sha256}\n"
            for item in lock.packages
        ),
        encoding="utf-8",
    )
    return list(needed.values())


def verify_installed(venv: Path, lock: Lock) -> None:
    """Inspect installed distribution metadata without starting plugin Python."""
    found: dict[str, str] = {}
    for path in (venv / "lib").glob("python*/site-packages/*.dist-info/METADATA"):
        with path.open("rb") as source:
            raw = source.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise PluginError("installed_dependencies_mismatch")
        metadata = Parser(policy=policy.default).parsestr(raw.decode("utf-8"))
        name = canonical_name(str(metadata["Name"]))
        if name in found:
            raise PluginError("installed_dependencies_mismatch")
        found[name] = str(metadata["Version"])
    if found != {item.name: item.version for item in lock.packages}:
        raise PluginError("installed_dependencies_mismatch")
