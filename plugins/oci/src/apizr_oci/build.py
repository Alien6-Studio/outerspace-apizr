"""Static service context preparation and verified local Docker image construction."""

import json
import os
import re
import stat
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from apizr.generators.mcp.generator import REQUIREMENTS as MCP_REQUIREMENTS
from apizr.generators.rest.generator import REQUIREMENTS as REST_REQUIREMENTS
from apizr.local_plugins.models import PluginError

from .model import BuildError, BuildRequest, BuildResult
from .process import run
from .snapshot import bundle_snapshot, input_digest, read, wheels_snapshot


def dockerfile(request: BuildRequest) -> str:
    command = (
        [
            "/opt/service/bin/python",
            "-B",
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ]
        if request.interface == "rest"
        else ["/opt/service/bin/python", "-B", "-u", "server.py"]
    )
    # No Dockerfile or shell fragment from the analyzed project is evaluated.
    # pip resolves the supplied closure, enforces hashes/tags/Python constraints,
    # and checks that the lock is exactly the canonical server dependency closure.
    return f"""FROM {request.base_image}
USER 0:0
ENV PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY wheels /opt/wheels
COPY requirements.lock /opt/requirements.lock
COPY server-requirements.txt /opt/server-requirements.txt
COPY locked-packages.json /opt/locked-packages.json
RUN python -m venv /opt/service && /opt/service/bin/python -m pip --isolated install --dry-run --ignore-installed --no-cache-dir --no-index --only-binary=:all: --find-links=/opt/wheels --report=/opt/report.json -r /opt/server-requirements.txt && /opt/service/bin/python -c 'import json,re; expected=json.load(open("/opt/locked-packages.json")); actual={{re.sub("[-_.]+", "-", p["metadata"]["name"]).lower():p["metadata"]["version"] for p in json.load(open("/opt/report.json"))["install"]}}; assert actual == expected, "lock must equal server dependency closure"' && /opt/service/bin/python -m pip --isolated install --no-cache-dir --no-compile --no-index --only-binary=:all: --require-hashes --find-links=/opt/wheels -r /opt/requirements.lock && /opt/service/bin/python -m pip --isolated check && rm -rf /opt/wheels /opt/report.json
COPY bundle /app
RUN chmod -R a+rX /app
USER 65532:65532
EXPOSE 8000
ENTRYPOINT {json.dumps(command)}
CMD []
"""


def build(
    request: BuildRequest, *, workspace: Path, cancel: Event | None = None
) -> BuildResult:
    """workspace must be caller-owned; the extension uses its runtime-owned CWD.

    Docker and wheels are trusted executables, not a sandbox. Only a successful
    image inspect confirms success. Terminating the client cannot certify daemon
    cancellation: caches or an unreported image can remain and are not pruned.
    """
    deadline = time.monotonic() + request.timeout_ms / 1000
    try:
        request = BuildRequest.model_validate(
            request.model_dump(by_alias=True), strict=True
        )
        try:
            available = os.access(request.docker.executable, os.X_OK) and stat.S_ISSOCK(
                os.stat(request.docker.socket).st_mode
            )
        except OSError:
            available = False
        if not available:
            raise BuildError("docker_unavailable")
        with TemporaryDirectory(prefix="oci-build-", dir=workspace) as directory:
            work = Path(directory)
            context = work / "context"
            context.mkdir(mode=0o700)
            bundle_snapshot(Path(request.bundle), context / "bundle", request.interface)
            expected = (
                REST_REQUIREMENTS if request.interface == "rest" else MCP_REQUIREMENTS
            )
            if (context / "bundle/requirements.txt").read_bytes() != expected:
                raise BuildError("unsupported_server_requirements")
            (context / "server-requirements.txt").write_bytes(expected)
            wheels_snapshot(
                Path(request.requirements), Path(request.wheelhouse), context
            )
            (context / "Dockerfile").write_text(dockerfile(request))
            (context / "target.json").write_text(
                json.dumps(
                    {"platform": request.platform, "interface": request.interface},
                    sort_keys=True,
                )
            )
            digest = input_digest(context)
            run(
                request,
                work,
                [
                    "build",
                    "--network=none",
                    "--load",
                    "--metadata-file",
                    str(work / "build-metadata.json"),
                    "--platform",
                    request.platform,
                    "--tag",
                    request.tag,
                    "--iidfile",
                    str(work / "image-id"),
                    "--label",
                    "sh.outerspace.apizr.inputs-sha256=" + digest,
                    "--file",
                    str(context / "Dockerfile"),
                    str(context),
                ],
                deadline,
                cancel,
            )
            image_id = read(work, "image-id", 128).decode().strip()
            if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
                raise BuildError("image_unverified")
            metadata = json.loads(read(work, "build-metadata.json", 1048576))
            identities = {
                metadata["containerimage.config.digest"],
                metadata["containerimage.digest"],
            }
            if (
                any(
                    re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
                    for value in identities
                )
                or image_id not in identities
            ):
                raise BuildError("image_unverified")
            actual = json.loads(
                run(request, work, ["image", "inspect", request.tag], deadline, cancel)
            )
            if (
                len(actual) != 1
                or re.fullmatch(r"sha256:[0-9a-f]{64}", actual[0]["Id"]) is None
                or actual[0]["Id"] not in identities
                or actual[0]["Os"] + "/" + actual[0]["Architecture"] != request.platform
                or actual[0]["Config"]["User"] != "65532:65532"
                or actual[0]["Config"]["Labels"].get(
                    "sh.outerspace.apizr.inputs-sha256"
                )
                != digest
            ):
                raise BuildError("image_unverified")
            return BuildResult(
                tag=request.tag,
                platform=request.platform,
                image_id=actual[0]["Id"],
                inputs_sha256=digest,
            )
    except BuildError:
        raise
    except PluginError as error:
        raise BuildError(str(error)) from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise BuildError("invalid_build_inputs") from None
