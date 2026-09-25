"""Pinned ORAS transport. No shell, tag fallback, inherited auth or Docker daemon."""

import hashlib
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from .model import Authentication, BuildError, Docker, Model, PushRequest
from .native import run
from .push import document, registry_authentication
from .snapshot import read

OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
IMAGE_MEDIA = {OCI_MANIFEST, "application/vnd.docker.distribution.manifest.v2+json"}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def digest_reference(value: str) -> str:
    repository, separator, digest = value.partition("@")
    if len(value) > 320 or not separator or DIGEST.fullmatch(digest) is None:
        raise ValueError("explicit digest reference required")
    PushRequest.reference(repository + ":explicit")
    return value


class OrasTool(Model):
    executable: str
    version: Literal["1.3.4"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    _path = field_validator("executable")(Docker.absolute.__func__)


class Transport(Model):
    tool: OrasTool
    authentication: Authentication
    max_candidates: int = Field(default=128, ge=1, le=128)
    max_discovery_bytes: int = Field(default=1048576, ge=1024, le=4194304)


def sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def descriptor(
    value, *, maximum=1048576, allowed: set[str] | frozenset[str] = frozenset()
):
    if (
        not isinstance(value, dict)
        or set(value) - {"mediaType", "digest", "size"} - allowed
        or not isinstance(value.get("mediaType"), str)
        or not isinstance(value.get("digest"), str)
        or DIGEST.fullmatch(value["digest"]) is None
        or type(value.get("size")) is not int
        or not 0 <= value["size"] <= maximum
    ):
        raise BuildError("invalid_oci_descriptor")
    return {k: value[k] for k in ("mediaType", "digest", "size")}


class Registry:
    def __init__(
        self, transport: Transport, reference: str, work: Path, deadline: float
    ):
        self.reference = digest_reference(reference)
        self.repository = reference.split("@")[0]
        self.work, self.deadline, self.transport = work, deadline, transport
        path = Path(transport.tool.executable)
        if not os.access(path, os.X_OK):
            raise BuildError("oras_unavailable")
        raw = read(path.parent, path.name, 128 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != transport.tool.sha256:
            raise BuildError("oras_binary_mismatch")
        self.executable = work / "oras-bin"
        fd = os.open(self.executable, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o700)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        version = run(self.executable, ["version"], work, deadline, 4096)
        if not version.splitlines() or version.splitlines()[0].split() != [
            b"Version:",
            b"1.3.4",
        ]:
            raise BuildError("unsupported_oras_version")
        registry_authentication(
            transport.authentication, self.repository.split("/")[0], work
        )
        self.flags = [
            "--plain-http=false",
            "--registry-config",
            str(work / "docker-config/config.json"),
        ]
        if transport.authentication.ca_file is not None:
            self.flags += ["--ca-file", str(work / "registry-ca.pem")]

    def call(
        self, args: list[str], *, maximum: int = 1048576, cwd: Path | None = None
    ) -> bytes:
        return run(
            self.executable,
            [*args, *self.flags],
            cwd or self.work,
            self.deadline,
            maximum + 65536,
            stdout_limit=maximum,
        )

    def manifest(self, reference: str):
        if digest_reference(reference).split("@")[0] != self.repository:
            raise BuildError("cross_repository_refused")
        raw = self.call(["manifest", "fetch", "--output", "-", reference])
        if sha(raw) != reference.split("@")[1]:
            raise BuildError("manifest_digest_mismatch")
        value = document(raw)
        if (
            not isinstance(value, dict)
            or value.get("schemaVersion") != 2
            or value.get("mediaType") not in IMAGE_MEDIA
        ):
            raise BuildError("single_manifest_required")
        return raw, {
            "mediaType": value["mediaType"],
            "digest": sha(raw),
            "size": len(raw),
        }

    def discover(self, artifact_type: str):
        raw = self.call(
            [
                "discover",
                "--distribution-spec",
                "v1.1-referrers-api",
                "--depth",
                "1",
                "--format",
                "json",
                "--artifact-type",
                artifact_type,
                self.reference,
            ],
            maximum=self.transport.max_discovery_bytes,
        )
        value = document(raw)
        if (
            not isinstance(value, dict)
            or value.get("reference") != self.reference
            or value.get("digest") != self.reference.split("@")[1]
        ):
            raise BuildError("invalid_oras_discovery")
        candidates = value.get("referrers")
        if not isinstance(candidates, list):
            raise BuildError("invalid_oras_discovery")
        if len(candidates) > self.transport.max_candidates:
            raise BuildError("discovery_limit_exceeded")
        found = {}
        for candidate in candidates:
            desc = descriptor(
                candidate,
                allowed={"reference", "artifactType", "annotations", "referrers"},
            )
            ref = self.repository + "@" + desc["digest"]
            if (
                candidate.get("reference") != ref
                or candidate.get("artifactType") != artifact_type
                or candidate.get("referrers") != []
                or desc["digest"] in found
            ):
                raise BuildError("invalid_oras_discovery")
            found[desc["digest"]] = desc | {
                "reference": ref,
                "artifact_type": artifact_type,
                "verified": False,
            }
        return [found[d] for d in sorted(found)]

    def blob(self, desc: dict) -> bytes:
        checked = descriptor(desc, allowed={"annotations"})
        raw = self.call(
            [
                "blob",
                "fetch",
                "--output",
                "-",
                self.repository + "@" + checked["digest"],
            ],
            maximum=checked["size"],
        )
        if len(raw) != checked["size"] or sha(raw) != checked["digest"]:
            raise BuildError("blob_integrity_failed")
        return raw
