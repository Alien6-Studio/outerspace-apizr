"""Read-only identity observation shared with optional delivery attestation."""

import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from .model import BuildError, PushRequest
from .push import authentication, local_identity, remote_observation, secure_daemon


@dataclass(frozen=True)
class Observation:
    config_digest: str
    manifest_digest: str
    manifest: bytes


def observe(
    request: PushRequest,
    reference: str,
    *,
    workspace: Path,
    cancel: Event | None = None,
) -> Observation:
    """Inspect the requested local ID and remote digest, never a mutable tag."""
    try:
        request = PushRequest.model_validate(request.model_dump(by_alias=True))
        repository, separator, digest = reference.partition("@")
        from .push import DIGEST

        if (
            not separator
            or repository != request.destination.rsplit(":", 1)[0]
            or DIGEST.fullmatch(digest) is None
        ):
            raise BuildError("invalid_digest_reference")
        if not os.access(request.docker.executable, os.X_OK) or not stat.S_ISSOCK(
            os.stat(request.docker.socket).st_mode
        ):
            raise BuildError("docker_unavailable")
        deadline = time.monotonic() + request.timeout_ms / 1000
        with TemporaryDirectory(prefix="oci-observe-", dir=workspace) as directory:
            work = Path(directory)
            authentication(request, work)
            local_identity(request, work, deadline, cancel)
            secure_daemon(request, work, deadline, cancel)
            value = remote_observation(request, work, reference, deadline, cancel)
            if value is None or value[1] != digest:
                raise BuildError("remote_manifest_unverified")
            return Observation(*value)
    except BuildError:
        raise
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise BuildError("oci_observation_refused") from None
