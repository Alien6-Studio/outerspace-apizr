"""Independent real syscalls: no Python API interposition is used as evidence."""

import json
import os
import sys

import anyio
import httpx
import pytest
from governed.helpers import SERVER, http_server
from governed_oci.helpers import bundle as single_bundle
from governed_oci.test_transports import remaining
from governed_repository.helpers import bundle as repository_bundle
from mcp import Client, StdioServerParameters
from oci.helpers import planned
from repository_execution.helpers import planned as repository_planned

from apizr.execution.policy import Subprocess
from apizr.execution.serialization import digest
from apizr.oci.model import ExecutionPolicyV2
from apizr.oci.supervisor import execute as allow_execute
from apizr.subprocess_guard.repository import execute as repository_execute
from apizr.subprocess_guard.single import execute

pytestmark = pytest.mark.timeout(180)

# All attempted operations use the real runtime/libc. With deny disabled they
# create a child or replace the process; successful probes leave an observable
# marker or change the worker's protocol result. The PID budget is deliberately
# spacious, so EPERM cannot be confused with PID exhaustion (EAGAIN).
SOURCE = b"""import _thread
import ctypes
import errno
import os
import platform
import subprocess
import sys
from pathlib import Path
IMPORT_DENIED = True

def probe(kind: str) -> bool:
    marker = Path("/tmp/child-executed")
    libc = ctypes.CDLL(None, use_errno=True)
    operation = kind
    try:
        if operation == "fork":
            pid = os.fork()
            if pid == 0:
                marker.touch()
                os._exit(0)
            os.waitpid(pid, 0)
        elif operation == "spawn":
            pid = os.posix_spawn(sys.executable, [sys.executable, "-c", "from pathlib import Path; Path('/tmp/child-executed').touch()"], {})
            os.waitpid(pid, 0)
        elif operation == "subprocess":
            subprocess.run([sys.executable, "-c", "from pathlib import Path; Path('/tmp/child-executed').touch()"], check=True)
        elif operation == "exec":
            os.execv(sys.executable, [sys.executable, "-c", "raise SystemExit(23)"])
        elif operation == "thread":
            try:
                _thread.start_new_thread(lambda: marker.touch(), ())
            except RuntimeError:
                return IMPORT_DENIED and not marker.exists()
        else:
            numbers = {"x86_64": {"raw-fork": 57, "raw-clone": 56, "raw-exec": 59, "raw-execat": 322}, "aarch64": {"raw-fork": 220, "raw-clone": 220, "raw-exec": 221, "raw-execat": 281}}
            number = {"raw-clone3": 435, "io-uring": 425}.get(operation, numbers[platform.machine()].get(operation))
            ctypes.set_errno(0)
            result = libc.syscall(ctypes.c_long(number), ctypes.c_ulong(17 if operation in {"raw-fork", "raw-clone"} and number in {56, 220} else 0), 0, 0, 0, 0, 0)
            if result == 0 and operation in {"raw-fork", "raw-clone"}:
                marker.touch()
                os._exit(0)
            if result > 0 and operation in {"raw-fork", "raw-clone"}:
                os.waitpid(result, 0)
            return result == -1 and ctypes.get_errno() == errno.EPERM and IMPORT_DENIED and not marker.exists()
    except OSError as error:
        return error.errno == errno.EPERM and IMPORT_DENIED and not marker.exists()
    return False
"""
KINDS = [
    "fork",
    "spawn",
    "subprocess",
    "exec",
    "thread",
    "raw-fork",
    "raw-clone",
    "raw-exec",
    "raw-execat",
    "raw-clone3",
    "io-uring",
]


def strict(value):
    policy = value.policy.model_copy(update={"subprocess": Subprocess(mode="deny")})
    return value.model_copy(update={"policy": policy, "policy_digest": digest(policy)})


@pytest.mark.parametrize("repository", [False, True])
def test_real_kernel_denies_all_creation_routes(worker_image, repository):
    before = remaining()
    if repository:
        runtime, exposure, sources, _ = repository_planned(
            SOURCE.replace(b"def probe(", b"def run("),
            policy=ExecutionPolicyV2(),
            image=worker_image,
        )
        for kind in KINDS:
            result = repository_execute(
                strict(runtime), exposure, sources, {"kind": kind}
            )
            assert result.status == "success" and result.value is True, (kind, result)
    else:
        raw = SOURCE.replace(b"def probe(", b"def f(")
        runtime, raw = planned(raw, image=worker_image)
        # Positive control proves the environment can create children when allowed.
        assert allow_execute(runtime, raw, {"kind": "subprocess"}).value is False
        for kind in KINDS:
            result = execute(strict(runtime), raw, {"kind": kind})
            assert result.status == "success" and result.value is True, (kind, result)
    assert remaining() == before


@pytest.mark.parametrize("repository", [False, True])
@pytest.mark.parametrize("transport", ["rest", "stdio", "streamable-http"])
def test_real_generated_transports_and_tamper(
    worker_image, tmp_path, repository, transport
):
    from apizr.oci.model import ExecutionPolicyV2

    policy = ExecutionPolicyV2(subprocess=Subprocess(mode="deny"))
    target = "rest" if transport == "rest" else "mcp"
    if repository:
        root = repository_bundle(
            tmp_path / "bundle",
            target,
            image=worker_image,
            policy=policy,
            files={"sample/api.py": SOURCE},
            selected=("python:sample.api:probe",),
        )
        contract = json.loads((root / "repository-interface.json").read_bytes())
        name = contract["capabilities"][0]["public_name"]
        route = "/capabilities/" + name
    else:
        root = single_bundle(
            tmp_path / "bundle",
            target,
            image=worker_image,
            policy=policy,
            source=SOURCE,
            select=["probe"],
        )
        name, route = "probe", "/capabilities/probe"
    damaged = root / "apizr_governed/subprocess_guard/provider.py"
    original = damaged.read_bytes()
    before = remaining()
    if transport == "rest":
        with http_server(root, "rest") as (url, _):
            with httpx.Client(base_url=url, timeout=15) as client:
                assert client.post(route, json={"kind": "raw-clone"}).json() is True
                damaged.write_bytes(original + b"# tampered\n")
                assert client.post(route, json={"kind": "fork"}).status_code == 500
                damaged.write_bytes(original)
                assert client.post(route, json={"kind": "spawn"}).json() is True
    else:

        async def check(connection):
            async with Client(connection, read_timeout_seconds=15) as client:
                assert (
                    await client.call_tool(name, {"kind": "raw-clone"})
                ).structured_content is True
                damaged.write_bytes(original + b"# tampered\n")
                assert (await client.call_tool(name, {"kind": "fork"})).is_error
                damaged.write_bytes(original)
                assert (
                    await client.call_tool(name, {"kind": "spawn"})
                ).structured_content is True

        if transport == "stdio":
            anyio.run(
                check,
                StdioServerParameters(
                    command=sys.executable,
                    args=["-I", "-c", SERVER, str(root), "stdio"],
                    cwd=root,
                    env=dict(os.environ),
                ),
            )
        else:
            with http_server(root, "mcp") as (url, _):
                anyio.run(check, url + "/mcp")
    assert remaining() == before


def test_repository_initializer_runs_after_filter(worker_image):
    files = {
        "sample/__init__.py": b"""import os
try:
    pid = os.fork()
except PermissionError:
    pass
else:
    if pid == 0: os._exit(0)
    os.waitpid(pid, 0)
    raise RuntimeError("filter was absent at project import")
""",
        "sample/api.py": b"def run(): return 42\n",
    }
    runtime, exposure, sources, _ = repository_planned(
        files=files, policy=ExecutionPolicyV2(), image=worker_image
    )
    result = repository_execute(strict(runtime), exposure, sources, {})
    assert result.status == "success" and result.value == 42
    from apizr.repository_execution.supervisor import execute as allow_repository

    assert allow_repository(runtime, exposure, sources, {}).status != "success"
