"""Publish a complete verified wheelhouse and empty profile, without installation."""

import json
import os
import tempfile
import time
import zipfile
from pathlib import Path
from threading import Event

from apizr.contracts.distribution import canonical_name
from apizr.plugins.artifacts.models import PluginError
from apizr.workspace.files import absolute_path, directory_fd, read_regular

from . import resolver, selection, target
from .models import (
    MAX_REQUIREMENTS_BYTES,
    Control,
    Pin,
    PreparationError,
    PreparationResult,
)
from .requirements import installer_lock, parse_resolver_lock


def serialize(result: PreparationResult) -> bytes:
    return (
        json.dumps(
            result.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def prepare_plugin(
    name: str,
    version: str,
    *,
    python: Path,
    platform: str,
    output_dir: Path,
    wheelhouse: Path | None = None,
    requirements: Path | None = None,
    index_url: str | None = None,
    uv: Path | None = None,
    timeout_ms: int = 120000,
    cancel: Event | None = None,
) -> PreparationResult:
    identity = None
    try:
        pin = Pin(name=canonical_name(name), version=version)
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600000:
            raise PreparationError("invalid_preparation_limits")
        control = Control(time.monotonic() + timeout_ms / 1000, cancel)
        control.check()
        if wheelhouse is None and index_url is None:
            raise PreparationError("artifact_source_required")
        output_dir = absolute_path(output_dir)
        # Match the existing catalog publication boundary: traverse parents
        # without following symlinks and hold that descriptor through publication.
        with directory_fd(output_dir.parent) as parent:
            if os.path.lexists(output_dir):
                raise PreparationError("output_exists")
            with tempfile.TemporaryDirectory(
                prefix=".apizr-preparation-", dir=output_dir.parent
            ) as temporary:
                work = Path(temporary)
                native = target.probe(python, platform, work, control)
                identity = native.identity
                retained = (
                    selection.snapshot(
                        absolute_path(wheelhouse), work / "inputs", control
                    )
                    if wheelhouse is not None
                    else None
                )
                tool = resolver.configure(
                    uv, python, native, retained, index_url, work, control
                )
                if requirements is None:
                    pins = resolver.resolve(tool, pin.name, pin.version, work, control)
                else:
                    pins = parse_resolver_lock(
                        read_regular(requirements, MAX_REQUIREMENTS_BYTES)
                    )
                if not any(
                    (item.name, item.version) == (pin.name, pin.version)
                    for item in pins
                ):
                    raise PreparationError(
                        "plugin_not_in_resolver_lock", pin.name, pin.version
                    )
                if index_url is None:
                    assert retained is not None
                    candidates = selection.local_candidates(retained, pins)
                else:
                    exact_pins = "".join(
                        f"{item.name}=={item.version}\n" for item in pins
                    ).encode()
                    evidence = resolver.compile_evidence(
                        tool, exact_pins, work, control, candidates=True
                    )
                    candidates = selection.resolver_candidates(evidence, pins, retained)
                export = work / "export"
                export.mkdir(mode=0o700)
                house = export / "wheelhouse"
                artifacts, manifest = selection.retain(
                    pins, candidates, identity, pin.name, house, work, control
                )
                normalized = installer_lock(artifacts)
                # Prove the selected wheel metadata is an installable closure
                # for this interpreter. This second resolution is always offline.
                offline = resolver.Resolver(
                    tool.executable, tool.version, python, native, house, None
                )
                verified = resolver.resolve(
                    offline, pin.name, pin.version, work, control
                )
                actual = {(item.name, item.version): item.hashes for item in verified}
                if actual != {
                    (item.name, item.version): (item.sha256,) for item in artifacts
                }:
                    raise PreparationError("resolver_lock_mismatch")
                (export / "requirements.lock").write_bytes(normalized)
                (export / "profile").mkdir(mode=0o700)
                result = PreparationResult(
                    state="prepared",
                    target=identity,
                    plugin=manifest,
                    artifacts=artifacts,
                    requirements="requirements.lock",
                    wheelhouse="wheelhouse",
                    profile="profile",
                    resolver=tool.version,
                    resolver_platform=native.resolver_platform,
                )
                (export / "preparation.json").write_bytes(serialize(result))
                control.check()
                try:
                    os.mkdir(output_dir.name, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    raise PreparationError("output_exists") from None
                try:
                    os.rename(export, output_dir.name, dst_dir_fd=parent)
                except BaseException:
                    os.rmdir(output_dir.name, dir_fd=parent)
                    raise
                return result
    except KeyboardInterrupt:
        error = PreparationError("preparation_cancelled")
    except PreparationError as problem:
        error = problem
    except PluginError as problem:
        error = PreparationError(str(problem))
    except zipfile.BadZipFile:
        error = PreparationError("invalid_wheel")
    except OSError:
        error = PreparationError("preparation_io_refused")
    except (ValueError, TypeError, RecursionError):
        error = PreparationError("invalid_preparation_input")
    diagnostic = error.diagnostic.model_copy(update={"target": identity})
    return PreparationResult(
        state="interrupted"
        if diagnostic.reason == "preparation_cancelled"
        else "refused",
        target=identity,
        diagnostics=(diagnostic,),
    )
