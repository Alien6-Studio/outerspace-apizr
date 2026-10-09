"""Static catalog inspection and atomic, portable export using project locks."""

import hashlib
import json
import os
import tempfile
from importlib.metadata import version
from pathlib import Path

from apizr.config_files import absolute_path, directory_fd, read_regular
from apizr.extension_runtime.protocol import unique_object
from apizr.plugins.local import locking
from apizr.plugins.local.wheel import MAX_WHEEL_BYTES
from apizr.plugins.lock import LockError, ProjectLock, create_lock, current_target
from apizr.plugins.lock.models import Plugin, Target, Wheel
from apizr.plugins.lock.operations import wheel_candidates

from .models import Catalog, CatalogError, Entry, Identity, Resolution

MAX_CATALOG_BYTES = 1024 * 1024


def serialize(catalog: Catalog) -> bytes:
    return (
        json.dumps(
            catalog.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def load_catalog(path: Path) -> Catalog:
    try:
        raw = read_regular(path, MAX_CATALOG_BYTES)
        document = json.loads(raw, object_pairs_hook=unique_object)
        return Catalog.model_validate_json(json.dumps(document), strict=True)
    except (OSError, ValueError, TypeError, RecursionError):
        raise CatalogError("invalid_catalog") from None


def select_entry(
    catalog: Catalog, name: str, exact_version: str, *, target: Target | None = None
) -> Entry:
    target = target or current_target()
    matches = [
        e
        for e in catalog.entries
        if (e.wheel.name, e.wheel.version) == (name, exact_version)
    ]
    if not matches:
        raise CatalogError("plugin_not_in_catalog")
    matches = [
        e
        for e in matches
        if e.compatibility.target == target
        and e.compatibility.apizr_version == version("outerspace-apizr")
    ]
    if not matches:
        raise CatalogError("incompatible_catalog_entry")
    if len(matches) != 1:
        raise CatalogError("ambiguous_catalog_entry")
    return matches[0]


def project_bytes(entries: tuple[Entry, ...]) -> bytes:
    lines = ['schema_version = "apizr.project/v1"', 'root = "."']
    for entry in sorted(entries, key=lambda e: e.wheel.name):
        lines.extend(("", "[[plugins]]"))
        for key in ("name", "version", "sha256"):
            lines.append(f"{key} = {json.dumps(getattr(entry.wheel, key))}")
        if entry.requirements:
            lines.append(f"requirements = {json.dumps(entry.requirements.path)}")
    return ("\n".join(lines) + "\n").encode()


def _plugin(entry: Entry) -> Plugin:
    def wheel(item):
        return Wheel.model_validate(item.model_dump(exclude={"size"}))

    return Plugin(
        manifest=entry.manifest,
        wheel=wheel(entry.wheel),
        dependencies=tuple(
            sorted((wheel(w) for w in entry.dependencies), key=lambda w: w.name)
        ),
        requirements=entry.requirements,
    )


def resolve_profile(
    catalog: Catalog, profile: str, wheelhouse: Path, output_dir: Path
) -> Resolution:
    """Verify local bytes and export. No subprocess, network or store access.

    The current exact lock target is intentional; this is not cross compilation
    or an installation qualification. uv checks dependency constraints at sync.
    """
    selected = next((p for p in catalog.profiles if p.name == profile), None)
    if selected is None:
        raise CatalogError("unknown_profile")
    entries = tuple(
        sorted(
            (select_entry(catalog, p.name, p.version) for p in selected.plugins),
            key=lambda e: e.wheel.name,
        )
    )
    output_dir = absolute_path(output_dir)
    try:
        # Parent traversal rejects symlinks. Keep that descriptor through publish.
        with directory_fd(output_dir.parent) as parent:
            if os.path.lexists(output_dir):
                # Never replace even an empty output: avoids racing other writers.
                raise CatalogError("output_exists")
            with tempfile.TemporaryDirectory(
                prefix=".apizr-catalog-", dir=output_dir.parent
            ) as temporary:
                root = Path(temporary)
                export = root / "export"
                export.mkdir(mode=0o700)
                (export / "requirements").mkdir(mode=0o700)
                house = root / "wheels"
                house.mkdir(mode=0o700)
                candidates = wheel_candidates(wheelhouse)
                retained: dict[str, bytes] = {}
                total = 0
                for entry in entries:
                    for wheel in (entry.wheel, *entry.dependencies):
                        names = candidates.get((wheel.name, wheel.version), [])
                        if len(names) > 1:
                            raise CatalogError("ambiguous_wheel")
                        if names != [wheel.filename]:
                            raise CatalogError("missing_wheel")
                        if wheel.filename not in retained:
                            payload = read_regular(
                                wheelhouse / wheel.filename, MAX_WHEEL_BYTES
                            )
                            total += len(payload)
                            if total > locking.MAX_TOTAL_BYTES:
                                raise CatalogError("artifacts_too_large")
                            retained[wheel.filename] = payload
                            (house / wheel.filename).write_bytes(payload)
                        payload = retained[wheel.filename]
                        if (
                            len(payload) != wheel.size
                            or hashlib.sha256(payload).hexdigest() != wheel.sha256
                        ):
                            raise CatalogError("wheel_mismatch")
                    if entry.requirements:
                        raw = read_regular(
                            wheelhouse / entry.requirements.path, locking.MAX_LOCK_BYTES
                        )
                        if (
                            hashlib.sha256(raw).hexdigest()
                            != entry.requirements.source_sha256
                        ):
                            raise CatalogError("requirements_mismatch")
                        (export / entry.requirements.path).write_bytes(raw)
                (export / "apizr.toml").write_bytes(project_bytes(entries))
                lock_path = export / "apizr.plugins.lock.json"
                outcome = create_lock(export / "apizr.toml", house, lock_path)
                if not outcome.valid:
                    raise CatalogError("catalog_artifacts_invalid")
                actual = ProjectLock.model_validate_json(
                    lock_path.read_bytes(), strict=True
                )
                expected = ProjectLock(
                    target=current_target(), plugins=tuple(_plugin(e) for e in entries)
                )
                if actual != expected:
                    raise CatalogError("catalog_artifacts_mismatch")
                files = tuple(
                    sorted(
                        str(p.relative_to(export))
                        for p in export.rglob("*")
                        if p.is_file()
                    )
                )
                result = Resolution(
                    profile=profile,
                    target=actual.target,
                    plugins=tuple(
                        Identity(name=e.wheel.name, version=e.wheel.version)
                        for e in entries
                    ),
                    files=files,
                )
                # mkdir reserves the final name exclusively; publishing one directory
                # rename never exposes a partial plan. Reservation is empty only.
                os.mkdir(output_dir.name, mode=0o700, dir_fd=parent)
                try:
                    os.rename(export, output_dir.name, dst_dir_fd=parent)
                except BaseException:
                    os.rmdir(output_dir.name, dir_fd=parent)
                    raise
                return result
    except (OSError, ValueError, LockError):
        raise CatalogError("catalog_export_failed") from None
