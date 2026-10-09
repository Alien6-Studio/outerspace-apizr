"""Resolver hash sets are evidence; the installer still receives one hash per pin."""

import re

from apizr.contracts.distribution import canonical_name
from apizr.plugins.artifacts.requirements import MAX_WHEELS, parse_lock

from .models import (
    MAX_HASHES,
    MAX_REQUIREMENTS_BYTES,
    AdmittedPin,
    Artifact,
    PreparationError,
)

PIN = r"([A-Za-z0-9][A-Za-z0-9._-]*)==([0-9][A-Za-z0-9.!+_]{0,127})"
LINE = re.compile(PIN + r"((?:\s+--hash=sha256:[0-9a-fA-F]{64})+)")
HASH = re.compile(r"--hash=sha256:([0-9a-fA-F]{64})")


def parse_resolver_lock(raw: bytes) -> tuple[AdmittedPin, ...]:
    if len(raw) > MAX_REQUIREMENTS_BYTES:
        raise PreparationError("resolver_lock_too_large")
    try:
        logical = re.sub(r"\\\r?\n", " ", raw.decode("utf-8"))
        pins: dict[str, AdmittedPin] = {}
        for line in logical.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # A whitespace-delimited annotation is permitted; URL fragments and
            # arbitrary options never become comments that hide invalid syntax.
            line = re.split(r"\s+#", line, maxsplit=1)[0].rstrip()
            match = LINE.fullmatch(line)
            if match is None:
                raise PreparationError("invalid_resolver_lock")
            name, version, hashes = match.groups()
            name = canonical_name(name)
            values = HASH.findall(hashes)
            if len(values) > MAX_HASHES or name in pins or len(pins) >= MAX_WHEELS:
                raise PreparationError("invalid_resolver_lock", name, version)
            pins[name] = AdmittedPin(
                name=name,
                version=version,
                hashes=tuple(sorted({value.lower() for value in values})),
            )
        if not pins:
            raise PreparationError("invalid_resolver_lock")
        return tuple(pins[name] for name in sorted(pins))
    except (ValueError, UnicodeError):
        raise PreparationError("invalid_resolver_lock") from None


def installer_lock(artifacts: tuple[Artifact, ...]) -> bytes:
    raw = "".join(
        f"{item.name}=={item.version} --hash=sha256:{item.sha256}\n"
        for item in sorted(artifacts, key=lambda item: item.name)
    ).encode("utf-8")
    # Keep the existing admission boundary authoritative, including its bounds.
    parse_lock(raw)
    return raw
