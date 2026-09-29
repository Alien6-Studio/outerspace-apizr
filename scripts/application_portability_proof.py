"""Qualification using the existing installed OCI plugin; no alternate builder."""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from operator_policy_proof import write_build_policy
from smoke_extension_packaging import snapshot

EXPECTED = "PORTABLE CAFÉ"


def exercise(
    repo, work, python, store, command, engine, base, platform, docker, socket, buildx
):
    # Imported here to reuse the existing lock helper without an import cycle.
    from smoke_oci_plugin import lock_wheels

    root = work / "application-proof"
    root.mkdir()
    project = root / "project"
    shutil.copytree(repo / "examples/application-inputs", project)
    (project / "unrelated.json").write_text("not declared")
    (project / ".env").write_text("not declared")
    core_before = snapshot(python.parent.parent)
    plugins_before = snapshot(store)
    absent = "import importlib.util; assert importlib.util.find_spec('six') is None"
    command(python, "-I", "-B", "-c", absent)
    # Both core and the actual isolated OCI plugin environment lack the dependency.
    plugin_python = next(store.glob("**/bin/python"))
    command(plugin_python, "-I", "-B", "-c", absent)
    operator = root / "analysis.json"
    operator.write_text(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": {"kind": "local", "root": str(project)},
                        "permissions": ["source.analyze"],
                    }
                ],
            }
        )
    )
    # Audit hook fails on execution/download; compile calls run in installed core.
    guard = """import sys,importlib.util
assert importlib.util.find_spec('six') is None
def guard(event,args):
    if event in ('subprocess.Popen','os.system','os.exec','socket.connect','socket.getaddrinfo'):
        raise AssertionError('analysis attempted external effects')
    if event == 'import' and args[0] in ('six','formatter'):
        raise AssertionError('analysis imported application')
sys.addaudithook(guard)
from apizr.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    bundles = {}
    for interface in ("rest", "mcp"):
        bundle = root / interface
        command(
            python,
            "-I",
            "-B",
            "-c",
            guard,
            "expose",
            "build",
            interface,
            "--project",
            project / "apizr.toml",
            "--operator-policy",
            operator,
            "--output-dir",
            bundle,
        )
        assert not (bundle / "source/unrelated.json").exists()
        assert not (bundle / "source/.env").exists()
        bundles[interface] = bundle
    images = []
    containers = []
    evidence = {
        "expected": EXPECTED,
        "analysis_without_application_dependency": True,
        "interfaces": {},
    }
    try:
        for interface, bundle in bundles.items():
            wheelhouse = root / (interface + "-wheels")
            wheelhouse.mkdir()
            requirements_in = root / (interface + ".in")
            requirements_in.write_bytes(
                (bundle / "requirements.txt").read_bytes()
                + (bundle / "application-requirements.txt").read_bytes()
            )
            engine(
                "run",
                "--rm",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--env",
                "HOME=/tmp",
                "--platform",
                platform,
                "--mount",
                f"type=bind,src={wheelhouse},dst=/wheels",
                "--mount",
                f"type=bind,src={requirements_in},dst=/requirements.txt,readonly",
                base,
                "python",
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--dest",
                "/wheels",
                "-r",
                "/requirements.txt",
            )
            lock = root / (interface + ".lock")
            lock_wheels(wheelhouse, lock)
            tag = "apizr-application-proof:" + interface + "-" + uuid.uuid4().hex[:12]
            images.append(tag)
            request = {
                "schema": "apizr.oci-build/v1",
                "bundle": str(bundle),
                "interface": interface,
                "base_image": base,
                "platform": platform,
                "tag": tag,
                "requirements": str(lock),
                "wheelhouse": str(wheelhouse),
                "docker": {
                    "executable": docker,
                    "socket": str(socket),
                    "buildx": str(buildx.resolve()) if buildx else None,
                },
                "timeout_ms": 300000,
                "max_log_bytes": 1048576,
            }
            path = root / (interface + "-build.json")
            path.write_text(json.dumps(request))
            authority = write_build_policy(
                python, store, root / (interface + "-operator.json"), request, command
            )
            result = json.loads(
                command(
                    python,
                    "-I",
                    "-B",
                    "-m",
                    "apizr.cli",
                    "plugins",
                    "run",
                    "outerspace-apizr-oci",
                    "build",
                    "--arguments",
                    path,
                    "--operator-policy",
                    authority,
                    "--plugins-dir",
                    store,
                    "--timeout-ms",
                    "360000",
                )
            )
            assert result["status"] == "ok" and not result["result"]["published"]
            image = json.loads(engine("image", "inspect", tag))[0]
            assert image["Id"] == result["result"]["image_id"] and not image[
                "Config"
            ].get("Volumes")
            evidence["interfaces"][interface] = result["result"]
        # Delete both the original source and generated bundles before either call.
        shutil.rmtree(project)
        for bundle in bundles.values():
            shutil.rmtree(bundle)
        assert not project.exists() and all(not b.exists() for b in bundles.values())
        container = engine("run", "--detach", "--publish", "127.0.0.1::8000", images[0])
        containers.append(container)
        assert json.loads(engine("inspect", container))[0]["Mounts"] == []
        address = engine("port", container, "8000/tcp").splitlines()[0]
        deadline = time.monotonic() + 30
        while True:
            try:
                request = urllib.request.Request(
                    "http://" + address + "/capabilities/formatter.message",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=2) as response:
                    observed = json.load(response)
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        assert observed == EXPECTED
        evidence["rest_result"] = observed
        client = root / "client"
        command("uv", "venv", "--python", sys.executable, client)
        command(
            "uv", "pip", "install", "--python", client / "bin/python", "mcp>=2.2,<3"
        )
        name = "apizr-application-mcp-" + uuid.uuid4().hex[:12]
        containers.append(name)
        command(
            client / "bin/python",
            "-I",
            "-c",
            """import asyncio,json,sys
from mcp import Client,StdioServerParameters
async def check():
    async with Client(StdioServerParameters(command=sys.argv[1],args=['--host',sys.argv[2],'run','--rm','--interactive','--name',sys.argv[3],sys.argv[4]],env={})) as client:
        assert [t.name for t in (await client.list_tools()).tools] == ['formatter.message']
        result=await client.call_tool('formatter.message',{})
        assert not result.is_error and result.structured_content == {'result':'PORTABLE CAFÉ'}
asyncio.run(check())
""",
            docker,
            "unix://" + str(socket),
            name,
            images[1],
            timeout=45,
        )
        evidence["mcp_result"] = {"result": EXPECTED}
        assert snapshot(python.parent.parent) == core_before
        assert snapshot(store) == plugins_before
        command(python, "-I", "-B", "-c", absent)
        command(plugin_python, "-I", "-B", "-c", absent)
        evidence.update(
            source_removed=True,
            bundles_removed=True,
            source_mounts=False,
            core_unchanged=True,
            plugin_store_unchanged=True,
        )
        (work / "application-portability.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
        )
        print(
            "PASS application portability: REST and MCP -> PORTABLE CAFÉ; source/bundles removed; core/plugins unchanged",
            flush=True,
        )
    finally:
        for container in containers:
            subprocess.run(
                [docker, "--host", "unix://" + str(socket), "rm", "--force", container],
                check=False,
                capture_output=True,
            )
        for tag in images:
            engine("image", "rm", tag)
