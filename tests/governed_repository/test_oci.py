"""Run the reviewed isolation probes against repository-aware workers, unchanged."""

import json
import os
import sys

import anyio
import httpx
import pytest
from governed.helpers import http_server
from governed_oci.test_transports import remaining
from mcp import Client, StdioServerParameters
from oci import test_integration as reviewed
from repository_execution.helpers import planned

from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_execution.docker import RepositoryDockerProvider
from apizr.repository_execution.supervisor import execute

from .helpers import bundle
from .test_transports import AUDITED

pytestmark = pytest.mark.timeout(180)


class Observed(RepositoryDockerProvider):
    name = None
    configuration = None

    def create_repository(self, name, plan, root, environment):
        super().create_repository(name, plan, root, environment)
        self.name = name
        self.configuration = json.loads(self.run(["inspect", name]))[0]

    def assert_removed(self):
        assert self.name
        assert not self.run(["ps", "-aq", "--filter", f"name=^/{self.name}$"]).strip()


def repository_plan(source, *, image, **changes):
    plan, exposure, sources, _ = planned(
        source.replace("def f(", "def run(").replace(
            "__file__", repr("/bundle/source/sample/api.py")
        ),
        policy=ExecutionPolicyV2.model_validate(changes),
        image=image,
    )
    return plan, (exposure, sources)


def repository_execute(plan, evidence, args, **kwargs):
    return execute(plan, *evidence, args, **kwargs)


def invoke(image, source, arguments=None, **changes):
    plan, evidence = repository_plan(source, image=image, **changes)
    provider = Observed()
    result = repository_execute(plan, evidence, arguments or {}, provider=provider)
    provider.assert_removed()
    return result, provider


@pytest.fixture
def repository_probes(monkeypatch):
    monkeypatch.setattr(reviewed, "invoke", invoke)
    monkeypatch.setattr(reviewed, "planned", repository_plan)
    monkeypatch.setattr(reviewed, "execute", repository_execute)
    monkeypatch.setattr(reviewed, "Observed", Observed)


@pytest.mark.parametrize(
    "probe",
    [
        "test_real_privilege_filesystem_and_resource_controls",
        "test_real_network_deny_with_host_listener",
        "test_real_pid_limit_contains_bounded_subprocess_loop",
        "test_real_readonly_mount_flags_cgroups_and_bounded_scratch",
        "test_real_detached_descendant_dies_with_container",
    ],
)
def test_reviewed_kernel_isolation(repository_probes, worker_image, tmp_path, probe):
    function = getattr(reviewed, probe)
    if probe == "test_real_privilege_filesystem_and_resource_controls":
        function(worker_image, tmp_path)
    else:
        function(worker_image)


def test_environment_allowlist(repository_probes, worker_image, monkeypatch):
    reviewed.test_real_environment_filter_and_no_values_in_arguments(
        worker_image, monkeypatch
    )


@pytest.mark.parametrize("transport", ["rest", "stdio", "streamable-http"])
def test_repeated_oom_and_exit137_transport_classification(
    worker_image, tmp_path, monkeypatch, transport
):
    files = {
        "sample/api.py": b"import os\ndef memory():\n chunks=[]\n for i in range(512): chunks.append(bytearray(1024*1024))\n return len(chunks)\ndef crash(): os._exit(137)\ndef loop():\n while True: pass\n"
    }
    root = bundle(
        tmp_path / "bundle",
        "rest" if transport == "rest" else "mcp",
        files=files,
        selected=tuple("python:sample.api:" + n for n in ("memory", "crash", "loop")),
        image=worker_image,
        policy=ExecutionPolicyV2.model_validate(
            {"limits": {"wall_time_ms": 2000}, "resources": {"memory_bytes": 100663296}}
        ),
    )
    monkeypatch.setattr("governed.helpers.SERVER", AUDITED)
    before = remaining()
    cases = [
        ("memory", 503, "Tool execution resource limit exceeded", 5),
        ("crash", 500, "Tool execution failed", 3),
        ("loop", 504, "Tool execution timed out", 2),
    ]
    if transport == "rest":
        with (
            http_server(root, "rest") as (url, process),
            httpx.Client(base_url=url, timeout=20) as client,
        ):
            for name, status, _, count in cases:
                for sample in range(count):
                    result = client.post("/capabilities/sample.api." + name, json={})
                    assert result.status_code == status, (name, sample, result.text)
                    assert remaining() == before
            assert process.poll() is None
    else:

        async def check(connection):
            async with Client(connection, read_timeout_seconds=20) as client:
                for name, _, message, count in cases:
                    for sample in range(count):
                        result = await client.call_tool("sample.api." + name, {})
                        assert result.is_error and result.content[0].text == message, (
                            name,
                            sample,
                            result,
                        )
                        assert remaining() == before

        if transport == "stdio":
            anyio.run(
                check,
                StdioServerParameters(
                    command=sys.executable,
                    args=["-I", "-c", AUDITED, str(root), "stdio"],
                    cwd=root,
                    env=dict(os.environ),
                ),
            )
        else:
            with http_server(root, "mcp") as (url, process):
                anyio.run(check, url + "/mcp")
                assert process.poll() is None
    assert remaining() == before
