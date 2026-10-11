"""Measured uv 0.12 resolution and artifact evidence; no installation or builds."""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from apizr.contracts.distribution import canonical_name
from apizr.plugins.artifacts._download_worker import DownloadFailure, validate_url

from .models import MAX_REQUIREMENTS_BYTES, AdmittedPin, Control, PreparationError
from .process import run
from .requirements import parse_resolver_lock
from .target import NativeTarget


@dataclass(frozen=True)
class Resolver:
    executable: str
    version: str
    python: Path
    target: NativeTarget
    wheelhouse: Path | None
    index_url: str | None


def configure(
    executable: Path | None,
    python: Path,
    target: NativeTarget,
    wheelhouse: Path | None,
    index_url: str | None,
    work: Path,
    control: Control,
) -> Resolver:
    if index_url is not None:
        try:
            parsed = validate_url(index_url)
            if parsed.query:
                raise ValueError()
        except (ValueError, DownloadFailure):
            raise PreparationError("invalid_index_url") from None
    found = str(executable) if executable is not None else shutil.which("uv")
    if found is None or not Path(found).is_absolute():
        raise PreparationError("resolver_unavailable")
    result = run([found, "--version"], work, control, max_stdout=8192)
    match = re.match(rb"uv (0\.12\.[0-9]+)(?:\s|$)", result.stdout)
    if result.code or match is None:
        raise PreparationError("resolver_version_unsupported")
    return Resolver(
        found, "uv " + match[1].decode(), python, target, wheelhouse, index_url
    )


def compile_evidence(
    resolver: Resolver,
    pins: bytes,
    work: Path,
    control: Control,
    *,
    candidates: bool = False,
) -> bytes:
    requirements = work / "resolver.in"
    requirements.write_bytes(pins)
    arguments = [
        resolver.executable,
        "--no-config",
        "--no-cache",
        "--no-progress",
        "--color",
        "never",
        "pip",
        "compile",
        str(requirements),
        "--generate-hashes",
        "--only-binary",
        ":all:",
        "--python",
        str(resolver.python),
        "--python-version",
        resolver.target.identity.python,
        "--no-python-downloads",
        "--no-header",
        "--no-annotate",
        "--no-sources",
    ]
    if candidates:
        arguments += ["--no-deps", "--universal", "--format", "pylock.toml"]
    else:
        arguments += ["--python-platform", resolver.target.resolver_platform]
    if resolver.index_url is None:
        arguments += ["--offline", "--no-index"]
    else:
        arguments += [
            "--default-index",
            resolver.index_url,
            "--keyring-provider",
            "disabled",
        ]
    if resolver.wheelhouse is not None:
        arguments += ["--find-links", str(resolver.wheelhouse)]
    environment = {
        "HOME": str(work),
        "TMPDIR": str(work),
        "UV_PYTHON_DOWNLOADS": "never",
        **resolver.target.environment,
    }
    result = run(arguments, work, control, environment=environment)
    if result.code:
        # Only extract a bounded canonical distribution identifier, never emit
        # resolver diagnostics, index credentials, input paths or command lines.
        evidence = re.search(
            rb"(?:Because |because )([A-Za-z0-9][A-Za-z0-9._-]{0,127})(?:==([0-9][A-Za-z0-9.!+_]{0,127}))? (?:has no usable wheels|was not found|has no wheels)",
            result.stderr,
        )
        if evidence is not None:
            raise PreparationError(
                "compatible_wheel_unavailable",
                canonical_name(evidence[1].decode()),
                evidence[2].decode() if evidence[2] else None,
            )
        raise PreparationError("resolver_refused")
    return result.stdout


def resolve(
    resolver: Resolver, name: str, version: str, work: Path, control: Control
) -> tuple[AdmittedPin, ...]:
    raw = compile_evidence(resolver, f"{name}=={version}\n".encode(), work, control)
    if len(raw) > MAX_REQUIREMENTS_BYTES:
        raise PreparationError("resolver_lock_too_large")
    return parse_resolver_lock(raw)
