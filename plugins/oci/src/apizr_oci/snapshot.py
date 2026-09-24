"""Copy only bounded declared artifacts, then validate the immutable private copy."""

import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath

from apizr.extension_runtime.protocol import unique_object
from apizr.local_plugins.locking import (
    MAX_TOTAL_BYTES,
    MAX_TOTAL_EXPANDED_BYTES,
    MAX_WHEELS,
    expanded_size,
    read_lock,
)
from apizr.local_plugins.models import canonical_name
from apizr.local_plugins.wheel import inspect_dependency
from apizr.repository_interfaces.model import MCPManifest, RestManifest
from apizr.repository_interfaces.runtime import validate_bundle

from .model import BuildError

MAX_BUNDLE_BYTES = 64 * 1024 * 1024
MAX_FILES = 4096
COMMON = {
    "repository-interface.json",
    "capability-catalog.json",
    "capability-graph.json",
    "repository-readiness.json",
    "exposure-policy.json",
    "exposure-plan.json",
    "apizr_repository_runtime.py",
    "apizr_runtime.py",
    "requirements.txt",
}


def read(root: Path, name: str, limit: int) -> bytes:
    path = PurePosixPath(name)
    if (
        not path.parts
        or path.is_absolute()
        or str(path) != name
        or ".." in path.parts
        or "\\" in name
    ):
        raise BuildError("invalid_bundle_path")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        fd = os.open(
            path.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise BuildError("regular_file_required")
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise BuildError("input_size_limit")
        return raw
    finally:
        os.close(descriptor)


def bundle_snapshot(source: Path, target: Path, interface: str) -> None:
    name = f"apizr-repository-{interface}.json"
    raw = read(source, name, 1048576)
    document = json.loads(raw, object_pairs_hook=unique_object)
    # Governed manifests have a different schema and additional artifacts.
    if document.get("schema_version") != f"apizr.repository-{interface}/v1":
        raise BuildError("direct_bundle_required")
    model = RestManifest if interface == "rest" else MCPManifest
    manifest = model.model_validate(document)
    allowed = COMMON | (
        {"app.py", "openapi.json"}
        if interface == "rest"
        else {"server.py", "mcp-tools.json"}
    )
    allowed |= {s.bundle_path for s in manifest.sources}
    if set(manifest.artifacts) != allowed or len(allowed) > MAX_FILES:
        raise BuildError("unsupported_bundle_artifacts")
    target.mkdir()
    (target / name).write_bytes(raw)
    total = len(raw)
    for artifact in sorted(allowed):
        raw = read(source, artifact, MAX_BUNDLE_BYTES - total)
        total += len(raw)
        destination = target / artifact
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    # This never calls load_bundle and never imports business code.
    validate_bundle(target, interface)


def wheels_snapshot(requirements: Path, wheelhouse: Path, target: Path) -> None:
    lock = read_lock(requirements)
    needed = {p.name: p for p in lock.packages}
    found = set()
    total = expanded = 0
    wheels = target / "wheels"
    wheels.mkdir()
    with os.scandir(wheelhouse) as entries:
        for count, entry in enumerate(entries, 1):
            if count > MAX_WHEELS:
                raise BuildError("too_many_wheels")
            if not entry.name.endswith(".whl"):
                raise BuildError("wheels_only")
            name = canonical_name(entry.name.split("-", 1)[0])
            if name not in needed or name in found:
                raise BuildError("unlocked_or_ambiguous_wheel")
            raw = read(
                wheelhouse, entry.name, min(64 * 1024 * 1024, MAX_TOTAL_BYTES - total)
            )
            destination = wheels / entry.name
            destination.write_bytes(raw)
            # Inspect the copied bytes, including archive/startup protections.
            data, actual = inspect_dependency(destination, needed[name].sha256)
            if actual != needed[name]:
                raise BuildError("dependency_lock_mismatch")
            total += len(data)
            expanded += expanded_size(data)
            if expanded > MAX_TOTAL_EXPANDED_BYTES:
                raise BuildError("wheelhouse_too_large")
            found.add(name)
    if found != set(needed):
        raise BuildError("missing_locked_wheel")
    (target / "requirements.lock").write_text(
        "".join(
            f"{p.name}=={p.version} --hash=sha256:{p.sha256}\n" for p in lock.packages
        )
    )
    (target / "locked-packages.json").write_text(
        json.dumps({p.name: p.version for p in lock.packages}, sort_keys=True)
    )


def input_digest(root: Path) -> str:
    entries = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
