"""Bounded Docker client I/O. Client exit is not evidence of daemon cancellation."""

import os
import selectors
import subprocess
import time
from pathlib import Path
from threading import Event

from .model import BuildError, BuildRequest


def run(
    request: BuildRequest,
    work: Path,
    arguments: list[str],
    deadline: float,
    cancel: Event | None = None,
) -> bytes:
    config = work / "docker-config"
    config.mkdir(exist_ok=True)
    if request.docker.buildx is not None:
        executable = Path(request.docker.buildx)
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise BuildError("buildx_unavailable")
        plugins = config / "cli-plugins"
        plugins.mkdir(exist_ok=True)
        link = plugins / "docker-buildx"
        if not link.is_symlink():
            link.symlink_to(executable)
    environment = {
        "HOME": str(work),
        "DOCKER_CONFIG": str(config),
        "DOCKER_HOST": "unix://" + request.docker.socket,
        "PATH": str(Path(request.docker.executable).parent)
        + ":/usr/local/bin:/usr/bin:/bin",
        "DOCKER_BUILDKIT": "1",
        "BUILDX_NO_DEFAULT_ATTESTATIONS": "1",
    }
    process = None
    try:
        if cancel is not None and cancel.is_set():
            raise BuildError("build_cancelled_daemon_state_unknown")
        if time.monotonic() >= deadline:
            raise BuildError("build_timeout_daemon_state_unknown")
        # Remain in the extension's owned group so its runtime can also reap
        # ordinary Docker/buildx descendants on timeout or external interruption.
        process = subprocess.Popen(
            [request.docker.executable, *arguments],
            cwd=work,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            bufsize=0,
        )
        assert process.stdout is not None and process.stderr is not None
        result = bytearray()
        count = 0
        with selectors.DefaultSelector() as selector:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map() or process.poll() is None:
                if cancel is not None and cancel.is_set():
                    raise BuildError("build_cancelled_daemon_state_unknown")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BuildError("build_timeout_daemon_state_unknown")
                for key, _ in selector.select(min(0.05, remaining)):
                    raw = os.read(key.fd, min(65536, request.max_log_bytes + 1 - count))
                    if not raw:
                        selector.unregister(key.fileobj)
                    else:
                        count += len(raw)
                        if count > request.max_log_bytes:
                            raise BuildError("docker_output_limit_daemon_state_unknown")
                        if key.fileobj is process.stdout:
                            result.extend(raw)
        if process.returncode:
            raise BuildError("docker_command_failed")
        return bytes(result)
    except OSError:
        raise BuildError("docker_unavailable") from None
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=2)
            finally:
                if process.stdout is not None:
                    process.stdout.close()
                if process.stderr is not None:
                    process.stderr.close()
