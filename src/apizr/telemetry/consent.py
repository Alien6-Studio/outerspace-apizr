"""Explicit per-user consent only: no event storage, identifier or project config."""

import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class Consent:
    requested: bool
    context_allows: bool
    enabled: bool
    reason: str


def preference_path(environ: Mapping[str, str]) -> Path:
    explicit = environ.get("APIZR_TELEMETRY_CONFIG")
    if explicit is not None:
        path = Path(explicit)
    elif sys.platform == "win32":
        path = (
            Path(environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
            / "Apizr/telemetry.json"
        )
    elif sys.platform == "darwin":
        path = Path.home() / "Library/Application Support/Apizr/telemetry.json"
    else:
        path = (
            Path(environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
            / "apizr/telemetry.json"
        )
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid_telemetry_config")
    return path


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _read(path: Path) -> bool | None:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError()
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_size > 512
            or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise ValueError()
        raw = os.read(descriptor, 513)
    finally:
        os.close(descriptor)
    if len(raw) > 512:
        raise ValueError()
    decoded: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    if not isinstance(decoded, dict):
        raise ValueError()
    value = cast(dict[str, object], decoded)
    if (
        set(value) != {"schema_version", "enabled"}
        or value["schema_version"] != "apizr.telemetry-consent/v1"
        or type(value["enabled"]) is not bool
    ):
        raise ValueError()
    return value["enabled"]


def decision(*, environ: Mapping[str, str] | None = None) -> Consent:
    env = os.environ if environ is None else environ
    requested = env.get("APIZR_TELEMETRY") == "1"
    allows = (
        env.get("CI", "").lower() in ("", "0", "false")
        and env.get("APIZR_TELEMETRY_ALLOWED", "1") == "1"
        and env.get("APIZR_SERVED_PROCESS") != "1"
        and env.get("APIZR_EXPERIMENT_RUNNER") != "1"
    )
    if not allows or env.get("APIZR_TELEMETRY") == "0":
        return Consent(requested, allows, False, "context_disabled")
    try:
        saved = _read(preference_path(env))
    except (OSError, ValueError, RecursionError):
        return Consent(requested, allows, False, "invalid_preferences")
    enabled = saved is not False and (saved is True or requested)
    return Consent(
        requested or saved is True,
        allows,
        enabled,
        "opted_in" if enabled else "default_off",
    )


def _write(enabled: bool, environ: Mapping[str, str] | None) -> Consent:
    env = os.environ if environ is None else environ
    temporary: str | None = None
    try:
        path = preference_path(env)
        if path.is_symlink():
            raise ValueError()
        _read(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".telemetry-", dir=path.parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(
                json.dumps(
                    {
                        "schema_version": "apizr.telemetry-consent/v1",
                        "enabled": enabled,
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, ValueError):
        raise ValueError("invalid_telemetry_config") from None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return decision(environ=env)


def enable(*, environ: Mapping[str, str] | None = None) -> Consent:
    current = decision(environ=environ)
    if not current.context_allows:
        return current
    return _write(True, environ)


def disable(*, environ: Mapping[str, str] | None = None) -> Consent:
    from apizr.telemetry.collection import discard_all

    discard_all()
    return _write(False, environ)


def status(*, environ: Mapping[str, str] | None = None) -> Consent:
    return decision(environ=environ)
