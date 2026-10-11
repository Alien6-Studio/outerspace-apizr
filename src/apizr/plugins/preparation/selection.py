"""Select one compatible admitted wheel, retain its bytes, then verify its metadata."""

import hashlib
import io
import json
import os
import sys
import tomllib
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import Parser
from itertools import product
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from pydantic import TypeAdapter

from apizr.contracts.distribution import canonical_name
from apizr.plugins.artifacts import _download_worker
from apizr.plugins.artifacts.models import Manifest, PluginError
from apizr.plugins.artifacts.requirements import (
    MAX_TOTAL_BYTES,
    MAX_TOTAL_EXPANDED_BYTES,
    MAX_WHEELS,
    expanded_size,
)
from apizr.plugins.artifacts.wheel import (
    MAX_METADATA_BYTES,
    MAX_WHEEL_BYTES,
    inspect_dependency,
    inspect_wheel,
)
from apizr.plugins.lock.models import Target, Wheel
from apizr.workspace.files import absolute_path, directory_fd, read_regular

from .models import (
    MAX_CANDIDATES,
    AdmittedPin,
    Artifact,
    Control,
    Pin,
    PreparationError,
)
from .process import run
from .target import supported_tags

OBJECTS = TypeAdapter(list[dict[str, Any]])
OPTIONAL_TEXT: TypeAdapter[str | None] = TypeAdapter(str | None)
HASHES = TypeAdapter(dict[str, str])


@dataclass(frozen=True)
class Candidate:
    filename: str
    sha256: str
    path: Path | None = None
    url: str | None = None


def snapshot(source: Path, destination: Path, control: Control) -> Path:
    destination.mkdir(mode=0o700)
    total = expanded = 0
    with directory_fd(source) as descriptor, os.scandir(descriptor) as entries:
        for count, entry in enumerate(entries, 1):
            control.check()
            if count > MAX_CANDIDATES:
                raise PreparationError("too_many_artifact_candidates")
            if not entry.name.endswith(".whl"):
                continue
            if not entry.is_file(follow_symlinks=False):
                raise PreparationError("regular_wheel_required")
            raw = read_regular(source / entry.name, MAX_WHEEL_BYTES)
            total += len(raw)
            expanded += expanded_size(raw)
            if total > MAX_TOTAL_BYTES or expanded > MAX_TOTAL_EXPANDED_BYTES:
                raise PreparationError("wheelhouse_too_large")
            retained = destination / entry.name
            retained.write_bytes(raw)
            # Structural validation precedes offering untrusted local wheels to uv.
            inspect_dependency(retained, hashlib.sha256(raw).hexdigest())
    return destination


def local_candidates(
    source: Path, pins: tuple[AdmittedPin, ...]
) -> dict[str, list[Candidate]]:
    wanted = {pin.name: pin.version for pin in pins}
    result: dict[str, list[Candidate]] = {pin.name: [] for pin in pins}
    for path in sorted(source.iterdir()):
        parts = path.name[:-4].split("-")
        if len(parts) not in (5, 6):
            raise PreparationError("invalid_wheel_filename")
        name = canonical_name(parts[0])
        if wanted.get(name) == parts[1]:
            raw = read_regular(path, MAX_WHEEL_BYTES)
            result[name].append(
                Candidate(path.name, hashlib.sha256(raw).hexdigest(), path=path)
            )
    return result


def resolver_candidates(
    raw: bytes, pins: tuple[AdmittedPin, ...], local: Path | None
) -> dict[str, list[Candidate]]:
    try:
        document = tomllib.loads(raw.decode("utf-8"))
        if document.get("lock-version") != "1.0" or document.get("created-by") != "uv":
            raise ValueError()
        packages = OBJECTS.validate_python(document["packages"], strict=True)
        if len(packages) != len(pins):
            raise ValueError()
        wanted = {pin.name: pin.version for pin in pins}
        result: dict[str, list[Candidate]] = {}
        count = 0
        for package in packages:
            package_pin = Pin(name=package["name"], version=package["version"])
            name, version = package_pin.name, package_pin.version
            if name in result or wanted.get(name) != version:
                raise ValueError()
            if any(key in package for key in ("sdist", "archive", "directory", "vcs")):
                raise PreparationError("compatible_wheel_unavailable", name, version)
            wheels = OBJECTS.validate_python(package.get("wheels", []), strict=True)
            result[name] = []
            for wheel in wheels:
                count += 1
                if count > MAX_CANDIDATES:
                    raise PreparationError("too_many_artifact_candidates")
                url = OPTIONAL_TEXT.validate_python(wheel.get("url"), strict=True)
                path = OPTIONAL_TEXT.validate_python(wheel.get("path"), strict=True)
                if (url is None) == (path is None):
                    raise ValueError()
                declared = HASHES.validate_python(wheel["hashes"], strict=True)
                if url is not None and url.startswith("file:"):
                    parsed = urlsplit(url)
                    if parsed.netloc or parsed.query or parsed.fragment:
                        raise ValueError()
                    path, url = unquote(parsed.path, errors="strict"), None
                if url is not None:
                    filename = _download_worker.wheel_filename(url)
                    retained_path = None
                    digest = declared["sha256"]
                else:
                    assert path is not None
                    retained_path = absolute_path(Path(path))
                    if local is None or retained_path.parent != absolute_path(local):
                        raise ValueError()
                    filename = retained_path.name
                    digest = hashlib.sha256(
                        read_regular(retained_path, MAX_WHEEL_BYTES)
                    ).hexdigest()
                    if declared and declared.get("sha256") != digest:
                        raise ValueError()
                identity = Wheel(
                    name=name,
                    version=version,
                    filename=filename,
                    sha256=digest,
                )
                parts = filename[:-4].split("-")
                if (
                    len(parts) not in (5, 6)
                    or canonical_name(parts[0]) != name
                    or parts[1] != version
                ):
                    raise ValueError()
                result[name].append(
                    Candidate(filename, identity.sha256, path=retained_path, url=url)
                )
        return result
    except (
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
        _download_worker.DownloadFailure,
    ):
        raise PreparationError("invalid_resolver_artifacts") from None


def select(pin: AdmittedPin, candidates: list[Candidate], target: Target) -> Candidate:
    priorities = supported_tags(target)
    ranked: list[tuple[int, Candidate]] = []
    for candidate in candidates:
        components = candidate.filename[:-4].rsplit("-", 3)[-3:]
        combinations = 1
        for component in components:
            combinations *= len(component.split("."))
        if combinations > MAX_CANDIDATES:
            raise PreparationError("invalid_wheel_tags", pin.name, pin.version)
        ranks = [
            priorities[tag]
            for parts in product(*(part.split(".") for part in components))
            if (tag := "-".join(parts)) in priorities
        ]
        if ranks:
            ranked.append((min(ranks), candidate))
    if not ranked:
        raise PreparationError("compatible_wheel_unavailable", pin.name, pin.version)
    best = min(rank for rank, _ in ranked)
    compatible = [candidate for rank, candidate in ranked if rank == best]
    if len(compatible) != 1:
        raise PreparationError("wheel_selection_ambiguous", pin.name, pin.version)
    selected = compatible[0]
    if selected.sha256 not in pin.hashes:
        raise PreparationError("wheel_hash_not_admitted", pin.name, pin.version)
    return selected


def _wheel_tags(data: bytes, filename: str) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [
            name for name in archive.namelist() if name.endswith(".dist-info/WHEEL")
        ]
        if len(names) != 1:
            raise PreparationError("invalid_wheel_tags")
        with archive.open(names[0]) as stream:
            raw = stream.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise PreparationError("invalid_wheel_tags")
        metadata = Parser(policy=policy.default).parsestr(raw.decode("utf-8"))
        tags = metadata.get_all("Tag", [])
        components = filename[:-4].rsplit("-", 3)[-3:]
        expected = {
            "-".join(tag) for tag in product(*(part.split(".") for part in components))
        }
        if metadata.defects or set(tags) != expected:
            raise PreparationError("invalid_wheel_tags")


def retain(
    pins: tuple[AdmittedPin, ...],
    candidates: dict[str, list[Candidate]],
    target: Target,
    plugin_name: str,
    house: Path,
    work: Path,
    control: Control,
) -> tuple[tuple[Artifact, ...], Manifest]:
    if len(pins) > MAX_WHEELS or plugin_name not in {pin.name for pin in pins}:
        raise PreparationError("plugin_not_in_resolver_lock")
    house.mkdir(mode=0o700)
    artifacts: list[Artifact] = []
    manifest = None
    total = expanded = 0
    for pin in pins:
        control.check()
        selected = select(pin, candidates.get(pin.name, []), target)
        destination = house / selected.filename
        if selected.path is not None:
            data = read_regular(selected.path, MAX_WHEEL_BYTES)
            destination.write_bytes(data)
        else:
            assert selected.url is not None
            request: _download_worker.Transfer = {
                "url": selected.url,
                "destination": str(destination),
                "sha256": selected.sha256,
                "max_bytes": min(MAX_WHEEL_BYTES, MAX_TOTAL_BYTES - total),
                "connect_timeout_ms": 5000,
                "read_timeout_ms": 10000,
                "ca_file": None,
            }
            control_file = work / "transfer.json"
            control_file.write_text(json.dumps(request), encoding="utf-8")
            result = run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(Path(_download_worker.__file__).resolve()),
                    str(control_file),
                ],
                work,
                control,
                max_stdout=8192,
            )
            if result.code:
                reason = (
                    "wheel_hash_not_admitted"
                    if result.code == 7
                    else "artifact_download_failed"
                )
                raise PreparationError(reason, pin.name, pin.version)
            data = read_regular(destination, MAX_WHEEL_BYTES)
        digest = hashlib.sha256(data).hexdigest()
        if digest not in pin.hashes or digest != selected.sha256:
            raise PreparationError("wheel_hash_not_admitted", pin.name, pin.version)
        try:
            _, actual = inspect_dependency(destination, digest)
            if (actual.name, actual.version) != (pin.name, pin.version):
                raise PluginError("dependency_lock_mismatch")
            _wheel_tags(data, selected.filename)
            if pin.name == plugin_name:
                _, manifest = inspect_wheel(
                    destination, digest, allow_dependencies=True
                )
            total += len(data)
            expanded += expanded_size(data)
        except PluginError as error:
            raise PreparationError(str(error), pin.name, pin.version) from None
        if total > MAX_TOTAL_BYTES or expanded > MAX_TOTAL_EXPANDED_BYTES:
            raise PreparationError("wheelhouse_too_large", pin.name, pin.version)
        artifacts.append(
            Artifact(
                name=pin.name,
                version=pin.version,
                filename=selected.filename,
                sha256=digest,
                size=len(data),
                admitted_hashes=pin.hashes,
            )
        )
    assert manifest is not None
    return tuple(sorted(artifacts, key=lambda item: item.name)), manifest
