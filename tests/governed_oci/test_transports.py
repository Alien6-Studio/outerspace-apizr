import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import anyio
import httpx
import pytest
from governed.helpers import SERVER, http_server
from mcp import Client, StdioServerParameters

from apizr.oci.model import ExecutionPolicyV2

from .helpers import bundle

pytestmark = pytest.mark.timeout(180)


def remaining():
    return set(
        subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", "label=org.apizr.execution=oci-v1"],
            text=True,
        ).split()
    )


@contextmanager
def host_listener():
    address = (
        "127.0.0.1"
        if sys.platform == "darwin"
        else socket.gethostbyname(socket.gethostname())
    )
    with socket.socket() as listener:
        listener.bind((address, 0))
        listener.listen()
        listener.settimeout(1)
        port = listener.getsockname()[1]
        with socket.create_connection((address, port), timeout=1):
            peer, _ = listener.accept()
            peer.close()
        yield address, port
        listener.settimeout(0.1)
        with pytest.raises(TimeoutError):
            listener.accept()


def damage(root, path, mode="append"):
    target = root / path
    original = target.read_bytes()
    if mode == "image":
        value = json.loads(original)
        value["runtime"]["image"] = "sha256:" + "1" * 64
        target.write_text(json.dumps(value))
    else:
        target.write_bytes(original + b"changed")
    return target, original


@pytest.mark.parametrize("transport", ["rest", "stdio", "streamable-http"])
def test_real_transports_isolation_failures_state_and_tampering(
    worker_image, tmp_path, monkeypatch, transport
):
    marker = "transport-env-only-marker"
    monkeypatch.setenv("APIZR_TEST_SECRET", marker)
    # This guard runs in the fresh actual server interpreter. Only the separate
    # container worker may import/execute the target. No Python sandbox mocks.
    audited = SERVER.replace(
        '    if event=="exec"',
        '    if event=="import" and args[0]=="governed_sample":\n        raise RuntimeError("source imported in transport")\n    if event=="exec"',
    )
    monkeypatch.setattr("governed.helpers.SERVER", audited)
    target = "rest" if transport == "rest" else "mcp"
    root = bundle(
        tmp_path / "bundle",
        target,
        image=worker_image,
        policy=ExecutionPolicyV2.model_validate(
            {
                "limits": {"wall_time_ms": 5000, "max_output_bytes": 1024},
                "resources": {"memory_bytes": 100663296, "pids": 12},
            }
        ),
    )
    assert all(
        marker.encode() not in p.read_bytes() for p in root.rglob("*") if p.is_file()
    )
    private = tmp_path / "host-private"
    private.write_text("private-marker")
    before = remaining()
    with host_listener() as (host, port):
        arguments = {"host": host, "port": port, "host_path": str(private)}
        expected = {
            "reachable": False,
            "host_file": False,
            "source_readable": True,
            "bundle_ro": True,
            "root_ro": True,
            "scratch": "ok",
            "socket": False,
        }

        def cleaned():
            assert remaining() == before

        paths = [
            "source/governed_sample.py",
            "execution/policy.json",
            "execution/plans/total.json",
            "execution/bundle.json",
            "apizr_governed/oci/docker.py",
            "apizr_governed/execution/worker.py",
        ]
        if transport == "rest":
            with (
                http_server(root, "rest") as (url, process),
                httpx.Client(base_url=url, timeout=15) as client,
            ):

                def call(name, args=None):
                    return client.post(
                        "/capabilities/" + name, json={} if args is None else args
                    )

                assert call("isolation", arguments).json() == expected
                cleaned()
                assert call("counter").json() == call("counter").json() == [1, 1]
                assert call("environment").json() is False
                assert call("greet", {"name": "Ada"}).json() == "Hello Ada"
                assert call("total", {}).status_code == 422
                cleaned()
                assert 0 < call("children").json() < 12
                cleaned()
                for name in ["memory", "sleep", "loop", "crash", "fail", "large"]:
                    response = call(name, {"n": 2000} if name == "large" else {})
                    assert response.status_code == {
                        "memory": 503,
                        "sleep": 504,
                        "loop": 504,
                    }.get(name, 500), response.text
                    assert marker not in response.text
                    cleaned()
                    assert process.poll() is None
                    assert call("total", {"a": 1}).json() == 6
                for path in paths:
                    target_path, original = damage(root, path)
                    assert call("total", {"a": 1}).status_code == 500
                    cleaned()
                    target_path.write_bytes(original)
                    assert call("total", {"a": 1}).json() == 6
                target_path, original = damage(
                    root, "execution/plans/total.json", "image"
                )
                assert call("total", {"a": 1}).status_code == 500
                target_path.write_bytes(original)
                assert call("total", {"a": 1}).json() == 6
        else:

            async def check(connection):
                async with Client(connection, read_timeout_seconds=15) as client:

                    async def call(name, args=None):
                        return await client.call_tool(
                            name, {} if args is None else args
                        )

                    assert (
                        await call("isolation", arguments)
                    ).structured_content == expected
                    cleaned()
                    assert (
                        (await call("counter")).structured_content
                        == (await call("counter")).structured_content
                        == [1, 1]
                    )
                    assert (await call("environment")).structured_content is False
                    assert (
                        await call("greet", {"name": "Ada"})
                    ).structured_content == "Hello Ada"
                    assert (await call("total")).is_error
                    cleaned()
                    for name in ["memory", "sleep", "loop", "crash", "fail", "large"]:
                        response = await call(
                            name, {"n": 2000} if name == "large" else {}
                        )
                        assert response.is_error
                        assert response.content[0].text == {
                            "memory": "Tool execution resource limit exceeded",
                            "sleep": "Tool execution timed out",
                            "loop": "Tool execution timed out",
                        }.get(name, "Tool execution failed")
                        cleaned()
                        assert (await call("total", {"a": 1})).structured_content == 6
                    for path in paths:
                        target_path, original = damage(root, path)
                        assert (await call("total", {"a": 1})).content[
                            0
                        ].text == "Tool execution failed"
                        cleaned()
                        target_path.write_bytes(original)
                        assert (await call("total", {"a": 1})).structured_content == 6
                    target_path, original = damage(
                        root, "execution/plans/total.json", "image"
                    )
                    assert (await call("total", {"a": 1})).is_error
                    target_path.write_bytes(original)
                    assert (await call("total", {"a": 1})).structured_content == 6

            if transport == "stdio":
                connection = StdioServerParameters(
                    command=sys.executable,
                    args=["-I", "-c", audited, str(root), "stdio"],
                    cwd=root,
                    env=dict(os.environ),
                )
                anyio.run(check, connection)
            else:
                with http_server(root, "mcp") as (url, process):
                    anyio.run(check, url + "/mcp")
                    assert process.poll() is None
    assert remaining() == before


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_real_allowlisted_environment_has_no_automatic_disclosure(
    worker_image, tmp_path, monkeypatch, transport
):
    from fastapi.testclient import TestClient

    from apizr.governed_oci.mcp import create_server
    from apizr.governed_oci.rest import create_app
    from apizr.oci.docker import DockerProvider

    marker = "oci-transport-secret-marker"
    monkeypatch.setenv("APIZR_TEST_SECRET", marker)
    root = bundle(
        tmp_path / "bundle",
        transport,
        image=worker_image,
        policy=ExecutionPolicyV2.model_validate(
            {"environment": {"allow": ["APIZR_TEST_SECRET"]}}
        ),
    )
    assert all(
        marker.encode() not in p.read_bytes() for p in root.rglob("*") if p.is_file()
    )
    commands = []
    original = DockerProvider.run

    def observe(self, args, **kwargs):
        commands.append(args)
        return original(self, args, **kwargs)

    monkeypatch.setattr(DockerProvider, "run", observe)
    if transport == "rest":
        with TestClient(create_app(root)) as client:
            assert client.post("/capabilities/environment", json={}).json() is True
    else:

        async def check():
            async with Client(create_server(root)) as client:
                assert (
                    await client.call_tool("environment", {})
                ).structured_content is True

        anyio.run(check)
    assert marker not in json.dumps(commands)


def test_real_detached_child_cleanup_through_rest(worker_image, tmp_path):
    import concurrent.futures

    child = 'import os,time; os.setsid();\nwhile True:\n open("/tmp/heartbeat","w").write(str(time.monotonic_ns()))\n time.sleep(0.05)'
    raw = (
        f'import subprocess,sys,time\ndef detached():\n subprocess.Popen([sys.executable,"-c",{child!r}],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\n time.sleep(3600)\ndef healthy(): return 1'
    ).encode()
    root = bundle(
        tmp_path / "rest",
        "rest",
        source=raw,
        image=worker_image,
        policy=ExecutionPolicyV2.model_validate({"limits": {"wall_time_ms": 3500}}),
    )
    before = remaining()
    with (
        http_server(root, "rest") as (url, process),
        concurrent.futures.ThreadPoolExecutor() as executor,
    ):
        response = executor.submit(
            httpx.post, url + "/capabilities/detached", json={}, timeout=15
        )
        beats = []
        container = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len(set(beats)) < 2:
            created = remaining() - before
            if created:
                container = next(iter(created))
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        container,
                        "/usr/local/bin/python",
                        "-c",
                        'print(open("/tmp/heartbeat").read())',
                    ],
                    capture_output=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    beats.append(result.stdout)
            time.sleep(0.05)
        assert len(set(beats)) >= 2
        assert response.result(timeout=10).status_code == 504
        assert remaining() == before
        assert (
            subprocess.run(
                ["docker", "exec", container, "cat", "/tmp/heartbeat"],
                capture_output=True,
            ).returncode
            != 0
        )
        assert process.poll() is None
        assert (
            httpx.post(url + "/capabilities/healthy", json={}, timeout=15).json() == 1
        )
    assert remaining() == before


@pytest.mark.parametrize("fault", ["missing", "platform", "label", "volumes"])
def test_real_provider_refuses_bad_image_before_serving(worker_image, tmp_path, fault):
    from apizr.governed_oci.runtime import GovernedRuntime
    from apizr.oci.model import RuntimeImage

    image = worker_image
    preparation = None
    produced = None
    before = remaining()
    try:
        if fault == "missing":
            image = image.model_copy(update={"image": "sha256:" + "0" * 64})
        elif fault == "platform":
            image = image.model_copy(
                update={
                    "platform": "linux/amd64"
                    if image.platform == "linux/arm64"
                    else "linux/arm64"
                }
            )
        else:
            # Deliberate local fixture preparation only: no run, mount, source,
            # registry acquisition or publication. Execution never creates images.
            preparation = subprocess.check_output(
                ["docker", "create", "--pull=never", image.image], text=True
            ).strip()
            change = (
                "LABEL org.apizr.worker.protocol=incompatible"
                if fault == "label"
                else "VOLUME /unwanted"
            )
            produced = subprocess.check_output(
                ["docker", "commit", "--change", change, preparation], text=True
            ).strip()
            image = RuntimeImage(image=produced, platform=image.platform)
        for transport in ["rest", "mcp"]:
            root = bundle(
                tmp_path / transport,
                transport,
                image=image,
                source=b"def f(): return 1",
            )
            with pytest.raises(RuntimeError, match="provider unavailable or invalid"):
                GovernedRuntime(root, transport)
        assert remaining() == before
    finally:
        if preparation:
            subprocess.run(
                ["docker", "rm", "-f", "-v", preparation],
                check=True,
                capture_output=True,
            )
        if produced:
            subprocess.run(
                ["docker", "image", "rm", "--no-prune", produced],
                check=True,
                capture_output=True,
            )


@pytest.mark.parametrize("transport", ["rest", "stdio", "streamable-http"])
def test_repeated_oom_transport_classification(
    worker_image, tmp_path, monkeypatch, transport
):
    """Every sample must pass; no pass-until-success retries."""
    root = bundle(
        tmp_path / "bundle",
        "rest" if transport == "rest" else "mcp",
        image=worker_image,
        policy=ExecutionPolicyV2.model_validate(
            {
                "limits": {"wall_time_ms": 2000},
                "resources": {"memory_bytes": 100663296},
            }
        ),
        select=["memory", "crash", "loop"],
    )
    before = remaining()
    # Diagnostic evidence is recorded only by the test server, after classification.
    from pathlib import Path

    instrumentation = Path(__file__).with_name("observation.py")
    observed_server = SERVER.replace(
        'if sys.argv[2]=="rest":',
        f'runpy.run_path({str(instrumentation)!r})["install"](root)\nif sys.argv[2]=="rest":',
    )
    monkeypatch.setattr("governed.helpers.SERVER", observed_server)

    def observations():
        path = tmp_path / "observations.jsonl"
        evidence = (
            path.read_text().splitlines()[-1]
            if path.exists()
            else "No provider observations"
        )
        print("OCI provider evidence for failed invocation:", evidence)
        return "See captured provider evidence"

    cases = [("memory", 20), ("crash", 3), ("loop", 3)]
    if transport == "rest":
        with (
            http_server(root, "rest") as (url, process),
            httpx.Client(base_url=url, timeout=15) as client,
        ):
            for name, repetitions in cases:
                for sample in range(repetitions):
                    response = client.post("/capabilities/" + name, json={})
                    assert (
                        response.status_code
                        == {"memory": 503, "crash": 500, "loop": 504}[name]
                    ), (name, sample, response.text, observations())
                    assert remaining() == before
            assert process.poll() is None
    else:

        async def check(connection):
            async with Client(connection, read_timeout_seconds=15) as client:
                for name, repetitions in cases:
                    for sample in range(repetitions):
                        response = await client.call_tool(name, {})
                        assert response.is_error
                        assert (
                            response.content[0].text
                            == {
                                "memory": "Tool execution resource limit exceeded",
                                "crash": "Tool execution failed",
                                "loop": "Tool execution timed out",
                            }[name]
                        ), (name, sample, response, observations())
                        assert remaining() == before

        if transport == "stdio":
            anyio.run(
                check,
                StdioServerParameters(
                    command=sys.executable,
                    args=["-I", "-c", observed_server, str(root), "stdio"],
                    cwd=root,
                    env=dict(os.environ),
                ),
            )
        else:
            with http_server(root, "mcp") as (url, process):
                anyio.run(check, url + "/mcp")
                assert process.poll() is None
    assert remaining() == before
