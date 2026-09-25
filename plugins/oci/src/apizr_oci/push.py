"""Publish an immutable local image, then confirm its remote single manifest.

Docker requires a local tag to upload. A fresh private staging tag carries the
image selected by ID; only its verified remote digest is promoted to the user's
tag. Registry preflight is not a compare-and-swap lock. No remote deletion occurs.
"""

import base64
import binascii
import hashlib
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from apizr.extension_runtime.protocol import unique_object

from .model import Authentication, BuildError, PushRequest, PushResult
from .process import run
from .snapshot import read

LABEL = "sh.outerspace.apizr.inputs-sha256"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MEDIA = {
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
}


def document(raw: bytes):
    return json.loads(raw, object_pairs_hook=unique_object)


def authentication(request: PushRequest, work: Path) -> None:
    """Copy only a bounded, explicit auth record. No helper/config inheritance."""
    registry_authentication(
        request.authentication, request.destination.split("/", 1)[0], work
    )


def registry_authentication(auth: Authentication, registry: str, work: Path) -> None:
    """Shared explicit credentials snapshot for Docker and ORAS; no helpers."""
    source = Path(auth.config_file)
    config = document(read(source.parent, source.name, 65536))
    if not isinstance(config, dict) or set(config) != {"auths"}:
        raise BuildError("invalid_registry_authentication")
    auths = config["auths"]
    if not isinstance(auths, dict) or set(auths) != {registry}:
        raise BuildError("invalid_registry_authentication")
    record = auths[registry]
    if not isinstance(record, dict) or set(record) != {"auth"}:
        raise BuildError("invalid_registry_authentication")
    encoded = record["auth"]
    if not isinstance(encoded, str):
        raise BuildError("invalid_registry_authentication")
    try:
        credentials = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise BuildError("invalid_registry_authentication") from None
    if b":" not in credentials or any(c in credentials for c in (b"\0", b"\r", b"\n")):
        raise BuildError("invalid_registry_authentication")
    directory = work / "docker-config"
    directory.mkdir(mode=0o700)
    with open(
        directory / "config.json", "x", opener=lambda p, f: os.open(p, f, 0o600)
    ) as stream:
        # Docker uses this historical key for Hub, including explicitly named
        # docker.io images. Normalize only the caller-selected record; never
        # consult another credential store or inherit a Docker configuration.
        key = (
            "https://index.docker.io/v1/"
            if registry in {"docker.io", "index.docker.io"}
            else registry
        )
        json.dump({"auths": {key: record}}, stream)
    if auth.ca_file is not None:
        ca = Path(auth.ca_file)
        (work / "registry-ca.pem").write_bytes(read(ca.parent, ca.name, 1048576))


def local_identity(request: PushRequest, work: Path, deadline: float, cancel):
    actual = document(
        run(request, work, ["image", "inspect", request.image_id], deadline, cancel)
    )
    if not isinstance(actual, list) or len(actual) != 1:
        raise BuildError("local_image_unverified")
    image = actual[0]
    if (
        image["Id"] != request.image_id
        or image["Os"] + "/" + image["Architecture"] != request.platform
        or image["Config"]["Labels"].get(LABEL) != request.inputs_sha256
        or image["Config"]["User"] != "65532:65532"
    ):
        raise BuildError("local_image_unverified")
    # Build produces a single manifest. Never silently select a member of an index.
    descriptor = image.get("Descriptor")
    if descriptor is not None and descriptor["mediaType"] not in MEDIA:
        raise BuildError("single_manifest_required")


def secure_daemon(request: PushRequest, work: Path, deadline: float, cancel) -> None:
    """Refuse explicit daemon-wide insecure registry configuration."""
    info = document(
        run(
            request,
            work,
            ["info", "--format", "{{json .RegistryConfig}}"],
            deadline,
            cancel,
        )
    )
    registry = request.destination.split("/", 1)[0]
    if (
        any(not value.get("Secure", False) for value in info["IndexConfigs"].values())
        or any(
            cidr not in {"127.0.0.0/8", "::1/128"}
            for cidr in info["InsecureRegistryCIDRs"]
        )
        or registry.split(":", 1)[0].endswith(".localhost")
    ):
        raise BuildError("insecure_registry_configuration")


def remote_observation(
    request: PushRequest,
    work: Path,
    reference: str,
    deadline: float,
    cancel,
    *,
    absent=False,
):
    # Docker normalizes this documented Hub alias before producing diagnostics.
    registry, separator, repository = reference.partition("/")
    if registry == "index.docker.io" and separator:
        reference = "docker.io/" + repository
    raw = run(
        request,
        work,
        ["manifest", "inspect", "--verbose", reference],
        deadline,
        cancel,
        absent_reference=reference if absent else None,
    )
    remote = document(raw)
    if remote is None and absent:
        return None
    if not isinstance(remote, dict):
        raise BuildError("remote_manifest_unverified")
    descriptor = remote["Descriptor"]
    manifest = remote.get("SchemaV2Manifest") or remote.get("OCIManifest")
    if not isinstance(manifest, dict) or descriptor["mediaType"] not in MEDIA:
        raise BuildError("remote_manifest_unverified")
    payload = base64.b64decode(remote["Raw"], validate=True)
    if (
        document(payload) != manifest
        or "sha256:" + hashlib.sha256(payload).hexdigest() != descriptor["digest"]
    ):
        raise BuildError("remote_manifest_unverified")
    manifest_digest = descriptor["digest"]
    config_digest = manifest["config"]["digest"]
    platform = descriptor["platform"]
    if (
        manifest["schemaVersion"] != 2
        or manifest["mediaType"] not in MEDIA
        or not isinstance(manifest_digest, str)
        or DIGEST.fullmatch(manifest_digest) is None
        or not isinstance(config_digest, str)
        or DIGEST.fullmatch(config_digest) is None
        or platform["os"] + "/" + platform["architecture"] != request.platform
        or request.image_id not in {manifest_digest, config_digest}
    ):
        raise BuildError("remote_image_conflict")
    # The registry client fetches the config to populate platform; either the
    # classic config ID or containerd manifest ID ties these bytes to local inspect.
    return config_digest, manifest_digest, payload


def remote_identity(request, work, reference, deadline, cancel, *, absent=False):
    value = remote_observation(
        request, work, reference, deadline, cancel, absent=absent
    )
    return value[:2] if value is not None else None


def push(
    request: PushRequest, *, workspace: Path, cancel: Event | None = None
) -> PushResult:
    """A successful result confirms a digest, never promises an immutable tag.

    A failure after upload starts means remote state is unconfirmed. Temporary
    staging tags may remain in the registry. The caller owns workspace; the
    extension runtime also removes it if this process is forcibly interrupted.
    """
    upload_started = False
    deadline = time.monotonic() + request.timeout_ms / 1000
    try:
        request = PushRequest.model_validate(
            request.model_dump(by_alias=True), strict=True
        )
        if not os.access(request.docker.executable, os.X_OK) or not stat.S_ISSOCK(
            os.stat(request.docker.socket).st_mode
        ):
            raise BuildError("docker_unavailable")
        with TemporaryDirectory(prefix="oci-push-", dir=workspace) as directory:
            work = Path(directory)
            authentication(request, work)
            local_identity(request, work, deadline, cancel)
            secure_daemon(request, work, deadline, cancel)
            repository = request.destination.rsplit(":", 1)[0]
            verified = remote_identity(
                request, work, request.destination, deadline, cancel, absent=True
            )
            if verified is None:
                staging = repository + ":apizr-upload-" + uuid.uuid4().hex
                run(
                    request,
                    work,
                    ["image", "tag", request.image_id, staging],
                    deadline,
                    cancel,
                )
                # No user tag is used as the upload source. Only the newly created
                # staging alias is passed to Docker's tag-based upload interface.
                upload_started = True
                run(
                    request,
                    work,
                    ["image", "push", "--platform", request.platform, staging],
                    deadline,
                    cancel,
                )
                verified = remote_identity(request, work, staging, deadline, cancel)
                assert verified is not None
                # Recheck immediately before promotion; concurrent registry writers
                # can still race this check. Registry immutability is the remedy.
                current = remote_identity(
                    request, work, request.destination, deadline, cancel, absent=True
                )
                if current is None:
                    run(
                        request,
                        work,
                        [
                            "buildx",
                            "imagetools",
                            "create",
                            "--prefer-index=false",
                            "--tag",
                            request.destination,
                            repository + "@" + verified[1],
                        ],
                        deadline,
                        cancel,
                    )
                elif current != verified:
                    raise BuildError("remote_image_conflict")
            # Verify the destination, then the immutable retrieval reference.
            final = remote_identity(
                request, work, request.destination, deadline, cancel
            )
            reference = repository + "@" + verified[1]
            pinned = remote_identity(request, work, reference, deadline, cancel)
            if final != verified or pinned != verified:
                raise BuildError("remote_manifest_unverified")
            return PushResult(
                destination=request.destination,
                digest_reference=reference,
                platform=request.platform,
                image_id=request.image_id,
                config_digest=verified[0],
                manifest_digest=verified[1],
                inputs_sha256=request.inputs_sha256,
            )
    except BuildError:
        if upload_started:
            raise BuildError("remote_state_unconfirmed") from None
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        if upload_started:
            raise BuildError("remote_state_unconfirmed") from None
        raise BuildError("oci_push_refused") from None
