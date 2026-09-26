"""Explicit static locking, without network, subprocesses or plugin imports."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from apizr.config_files import absolute_path, directory_fd, read_regular
from apizr.extension_runtime.protocol import unique_object
from apizr.local_plugins import list_extensions, locking
from apizr.local_plugins.models import LockedDistribution, PluginError, canonical_name
from apizr.local_plugins.wheel import MAX_WHEEL_BYTES, inspect_dependency, inspect_wheel
from apizr.project import ProjectConfig, load_project

from .models import (
    Diagnostic,
    InstalledState,
    LockError,
    Plugin,
    ProjectLock,
    Requirements,
    Result,
    Target,
    Wheel,
    current_target,
)

MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_FILES = 512


def serialize(lock: ProjectLock) -> bytes:
    return (
        json.dumps(
            lock.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode()


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_project(path: Path) -> ProjectConfig:
    try:
        return load_project(path)
    except OSError:
        raise LockError("project_unreadable") from None
    except (ValueError, TypeError, RecursionError):
        raise LockError("invalid_project") from None


def _target_wheel(filename: str, target: Target) -> None:
    # Conservative static tag check, not pip/uv's platform compatibility resolver.
    python, abi, platform_tag = filename[:-4].rsplit("-", 3)[-3:]
    major, minor, _ = target.python.split(".")
    python_tags = {"py" + major, "py" + major + minor}
    if target.implementation == "cpython":
        python_tags.add("cp" + major + minor)
    platform_tags = {"any", target.platform.replace("-", "_").replace(".", "_")}
    abi_tags = {"none"}
    if target.implementation == "cpython":
        abi_tags.add("cp" + major + minor + ("t" if "t-" in target.abi else ""))
    if (
        not python_tags.intersection(python.split("."))
        or not abi_tags.intersection(abi.split("."))
        or not platform_tags.intersection(platform_tag.split("."))
    ):
        raise PluginError("wheel_target_not_verifiable")


def _candidates(wheelhouse: Path) -> dict[tuple[str, str], list[str]]:
    candidates: dict[tuple[str, str], list[str]] = {}
    try:
        with directory_fd(wheelhouse) as descriptor, os.scandir(descriptor) as entries:
            for count, entry in enumerate(entries, 1):
                if count > MAX_FILES:
                    raise LockError("too_many_wheelhouse_files")
                if not entry.name.endswith(".whl"):
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise LockError("regular_wheel_required")
                parts = entry.name[:-4].split("-")
                if len(parts) not in (5, 6):
                    raise LockError("invalid_wheel_filename")
                identity = (canonical_name(parts[0]), parts[1])
                candidates.setdefault(identity, []).append(entry.name)
    except (OSError, ValueError):
        raise LockError("wheelhouse_unreadable") from None
    return candidates


def _assemble(
    project: Path, wheelhouse: Path
) -> tuple[ProjectLock | None, tuple[Diagnostic, ...]]:
    config = _load_project(project)
    target = current_target()
    candidates = _candidates(wheelhouse)
    diagnostics: list[Diagnostic] = []
    plugins: list[Plugin] = []
    total = expanded = 0
    # Retain each selected input exactly once, even when closures share a wheel.
    retained: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="apizr-plugin-lock-") as temporary:
        snapshot = Path(temporary)
        for declaration in sorted(config.plugins, key=lambda item: item.name):
            requirements = None
            packages = (
                LockedDistribution(
                    name=declaration.name,
                    version=declaration.version,
                    sha256=declaration.sha256,
                ),
            )
            if declaration.requirements is not None:
                try:
                    raw = read_regular(
                        project.absolute().parent / declaration.requirements,
                        locking.MAX_LOCK_BYTES,
                    )
                    parsed = locking.parse_lock(raw)
                    requirements = Requirements(
                        path=declaration.requirements, source_sha256=parsed.sha256
                    )
                except OSError:
                    raise LockError("requirements_unreadable") from None
                except (ValueError, PluginError):
                    raise LockError("invalid_requirements") from None
                if packages[0] not in parsed.packages:
                    diagnostics.append(
                        Diagnostic(
                            code="plugin_requirements_mismatch", plugin=declaration.name
                        )
                    )
                    continue
                packages = parsed.packages
            wheels: list[Wheel] = []
            manifest = None
            for expected in packages:
                names = candidates.get((expected.name, expected.version), [])
                if len(names) != 1:
                    diagnostics.append(
                        Diagnostic(
                            code="missing_wheel" if not names else "ambiguous_wheel",
                            plugin=declaration.name,
                            distribution=expected.name,
                        )
                    )
                    continue
                filename = names[0]
                try:
                    if filename not in retained:
                        payload = read_regular(wheelhouse / filename, MAX_WHEEL_BYTES)
                        total += len(payload)
                        if total > locking.MAX_TOTAL_BYTES:
                            raise LockError("wheelhouse_too_large")
                        retained[filename] = payload
                        (snapshot / filename).write_bytes(payload)
                    payload = retained[filename]
                    if expected.name == declaration.name:
                        _, manifest = inspect_wheel(
                            snapshot / filename,
                            expected.sha256,
                            allow_dependencies=requirements is not None,
                        )
                        actual = LockedDistribution(
                            name=manifest.name,
                            version=manifest.version,
                            sha256=_digest(payload),
                        )
                    else:
                        _, actual = inspect_dependency(
                            snapshot / filename, expected.sha256
                        )
                    if actual != expected:
                        raise PluginError("dependency_lock_mismatch")
                    _target_wheel(filename, target)
                    expanded += locking.expanded_size(payload)
                    if expanded > locking.MAX_TOTAL_EXPANDED_BYTES:
                        raise LockError("wheelhouse_too_large")
                    wheels.append(Wheel(**expected.model_dump(), filename=filename))
                except PluginError as error:
                    diagnostics.append(
                        Diagnostic(
                            code=str(error),
                            plugin=declaration.name,
                            distribution=expected.name,
                        )
                    )
                except (OSError, ValueError):
                    raise LockError("wheel_unreadable") from None
            if manifest is not None and len(wheels) == len(packages):
                primary = next(item for item in wheels if item.name == declaration.name)
                plugins.append(
                    Plugin(
                        manifest=manifest,
                        wheel=primary,
                        dependencies=tuple(
                            sorted(
                                (
                                    item
                                    for item in wheels
                                    if item.name != declaration.name
                                ),
                                key=lambda item: item.name,
                            )
                        ),
                        requirements=requirements,
                    )
                )
    if diagnostics:
        return None, tuple(diagnostics)
    result = ProjectLock(target=target, plugins=tuple(plugins))
    if len(serialize(result)) > MAX_DOCUMENT_BYTES:
        raise LockError("lock_too_large")
    return result, ()


def _publish(path: Path, raw: bytes) -> None:
    """Exclusive hard-link publication: complete bytes or nothing; never replace."""
    path = absolute_path(path)
    temporary = ".apizr-lock-" + uuid4().hex
    try:
        with directory_fd(path.parent) as directory:
            try:
                descriptor = os.open(
                    temporary,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(
                        temporary,
                        path.name,
                        src_dir_fd=directory,
                        dst_dir_fd=directory,
                        follow_symlinks=False,
                    )
                except FileExistsError:
                    if read_regular(path, MAX_DOCUMENT_BYTES) != raw:
                        raise LockError("output_conflict") from None
            finally:
                os.unlink(temporary, dir_fd=directory)
    except (OSError, ValueError):
        raise LockError("output_unwritable") from None


def create_lock(project: Path, wheelhouse: Path, output: Path) -> Result:
    lock, diagnostics = _assemble(project, wheelhouse)
    if lock is None:
        return Result(valid=False, target=current_target(), diagnostics=diagnostics)
    raw = serialize(lock)
    _publish(output, raw)
    return Result(valid=True, target=lock.target, lock_sha256=_digest(raw))


def _read(path: Path) -> tuple[ProjectLock, bytes]:
    try:
        raw = read_regular(path, MAX_DOCUMENT_BYTES)
        document = json.loads(raw, object_pairs_hook=unique_object)
        lock = ProjectLock.model_validate_json(json.dumps(document), strict=True)
        # Invariants not expressed by individual wheel fields.
        names: set[str] = set()
        for plugin in lock.plugins:
            if plugin.wheel.name in names:
                raise ValueError()
            names.add(plugin.wheel.name)
            if (plugin.manifest.name, plugin.manifest.version) != (
                plugin.wheel.name,
                plugin.wheel.version,
            ):
                raise ValueError()
            distribution_names = [
                plugin.wheel.name,
                *(item.name for item in plugin.dependencies),
            ]
            if len(set(distribution_names)) != len(distribution_names) or (
                plugin.dependencies and plugin.requirements is None
            ):
                raise ValueError()
        return lock, raw
    except OSError:
        raise LockError("lock_unreadable") from None
    except (ValueError, TypeError, RecursionError):
        raise LockError("invalid_project_lock") from None


def check_lock(
    project: Path,
    lock_path: Path,
    wheelhouse: Path,
    *,
    installed: bool = False,
    directory: Path | None = None,
) -> Result:
    lock, raw = _read(lock_path)
    diagnostics: list[Diagnostic] = []
    states: list[InstalledState] = []
    if lock.target != current_target():
        diagnostics.append(Diagnostic(code="target_mismatch"))
    expected, artifact_diagnostics = _assemble(project, wheelhouse)
    diagnostics.extend(artifact_diagnostics)
    if expected is not None:
        wanted = {item.wheel.name: item for item in expected.plugins}
        recorded = {item.wheel.name: item for item in lock.plugins}
        for name in sorted(wanted.keys() | recorded.keys()):
            if wanted.get(name) != recorded.get(name):
                diagnostics.append(
                    Diagnostic(code="project_artifacts_changed", plugin=name)
                )
    if installed:
        try:
            inventory = list_extensions(directory=directory)
            active = list_extensions(directory=directory, active=True)
        except PluginError:
            raise LockError("inventory_unreadable") from None
        for plugin in lock.plugins:
            record = next(
                (
                    item
                    for item in inventory.installations
                    if (item.name, item.version)
                    == (plugin.wheel.name, plugin.wheel.version)
                ),
                None,
            )
            matches = record is not None and (
                record.sha256 == plugin.wheel.sha256
                and record.lock_sha256
                == (plugin.requirements.source_sha256 if plugin.requirements else None)
                and record.module == plugin.manifest.module
                and record.protocol == plugin.manifest.protocol
                and sorted(record.dependencies, key=lambda item: item.name)
                == [
                    LockedDistribution(
                        name=item.name, version=item.version, sha256=item.sha256
                    )
                    for item in plugin.dependencies
                ]
            )
            states.append(
                InstalledState(
                    name=plugin.wheel.name,
                    matches=matches,
                    active=record is not None and record in active.installations,
                )
            )
            if not matches:
                diagnostics.append(
                    Diagnostic(
                        code="installation_missing"
                        if record is None
                        else "installation_mismatch",
                        plugin=plugin.wheel.name,
                    )
                )
    return Result(
        valid=not diagnostics,
        lock_sha256=_digest(raw),
        target=lock.target,
        diagnostics=tuple(diagnostics),
        installed=tuple(states),
    )
