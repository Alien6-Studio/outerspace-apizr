"""Bounded HTTPS acquisition followed by the existing offline wheel installer."""

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event

from pydantic import ConfigDict, Field

from apizr.capabilities.types import ValueModel

from . import _download_worker, backend, wheel
from .models import Installation, PluginError
from .operations import install_extension


class DownloadLimits(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    connect_timeout_ms: int = Field(default=5000, ge=1, le=300000)
    read_timeout_ms: int = Field(default=10000, ge=1, le=300000)
    total_timeout_ms: int = Field(default=60000, ge=1, le=600000)


class DownloadCancelled(PluginError):
    def __init__(self) -> None:
        super().__init__("download_cancelled")


DEFAULT_LIMITS = DownloadLimits()


def _check_cancel(cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise DownloadCancelled()


def _download(
    request: _download_worker.Transfer,
    work: Path,
    limits: DownloadLimits,
    cancel: Event | None,
) -> None:
    control = work / "request.json"
    control.write_text(json.dumps(request), encoding="utf-8")
    control.chmod(0o600)
    deadline = time.monotonic() + limits.total_timeout_ms / 1000
    # Only TLS trust paths are inherited. No proxies, credentials or Python settings.
    environment = {
        key: os.environ[key]
        for key in ("SSL_CERT_FILE", "SSL_CERT_DIR")
        if key in os.environ
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(_download_worker.__file__).resolve()),
            str(control),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        cwd=work,
        start_new_session=True,
        close_fds=True,
        umask=0o077,
    )
    try:
        while True:
            _check_cancel(cancel)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PluginError("download_timeout")
            try:
                code = process.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                continue
            if code:
                raise PluginError(_download_worker.ERRORS.get(code, "download_failed"))
            _check_cancel(cancel)
            return
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise PluginError("download_cleanup_failed") from None


def install_from_url(
    url: str,
    sha256: str,
    *,
    directory: Path | None = None,
    python: Path | None = None,
    limits: DownloadLimits = DEFAULT_LIMITS,
    cancel: Event | None = None,
    ca_file: Path | None = None,
) -> Installation:
    """Verify a complete HTTPS wheel before delegating; cancellation covers acquisition."""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise PluginError("invalid_sha256")
    try:
        name = _download_worker.wheel_filename(url)
    except _download_worker.DownloadFailure as error:
        raise PluginError(str(error)) from None
    try:
        limits = DownloadLimits.model_validate(limits.model_dump(), strict=True)
    except ValueError:
        raise PluginError("invalid_download_limits") from None
    if os.name != "posix":
        raise PluginError("unsupported_platform")
    _check_cancel(cancel)
    backend.require_uv()
    try:
        with tempfile.TemporaryDirectory(prefix="apizr-download-") as temporary:
            work = Path(temporary)
            path = work / name
            request: _download_worker.Transfer = {
                "url": url,
                "destination": str(path),
                "sha256": sha256,
                "max_bytes": wheel.MAX_WHEEL_BYTES,
                "connect_timeout_ms": limits.connect_timeout_ms,
                "read_timeout_ms": limits.read_timeout_ms,
                "ca_file": str(ca_file.resolve()) if ca_file is not None else None,
            }
            _download(request, work, limits, cancel)
            _check_cancel(cancel)
            # inspect_wheel snapshots and rechecks these same private file bytes.
            # uv only receives that hash-checked snapshot, and stays offline.
            return install_extension(path, sha256, directory=directory, python=python)
    except OSError:
        raise PluginError("download_failed") from None


def install_from_source(
    source: str | Path,
    sha256: str,
    *,
    directory: Path | None = None,
    python: Path | None = None,
) -> Installation:
    """Keep paths offline; reject unsupported/malformed URL schemes explicitly."""
    if isinstance(source, str) and (
        re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", source.lstrip())
        or "://" in source
        or source.startswith("//")
    ):
        return install_from_url(source, sha256, directory=directory, python=python)
    return install_extension(Path(source), sha256, directory=directory, python=python)
