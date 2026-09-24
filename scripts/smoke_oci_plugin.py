"""Real REST/MCP images from Git and installed wheels, on a disposable Docker runner."""

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from email.parser import BytesParser
from pathlib import Path

from smoke_extension_packaging import snapshot
from smoke_git_source import exercise as git_bundles

REPO = Path(__file__).resolve().parents[1]


def run(args, *, cwd, env=None, timeout=600):
    print("+", " ".join(map(str, args)), flush=True)
    result = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def lock_wheels(house, path):
    lines = []
    for wheel in sorted(house.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            name = next(
                n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
            )
            metadata = BytesParser().parsebytes(archive.read(name))
        lines.append(
            f"{metadata['Name']}=={metadata['Version']} --hash=sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}\n"
        )
    path.write_text("".join(lines))


def refuse_builds(python, document, store, work, environment):
    """Real installed-plugin refusals, including pip's missing transitive closure."""
    inputs = work / "refused-build.json"
    bundle_file = Path(document["bundle"]) / "source/calculator.py"
    lock = Path(document["requirements"])
    house = Path(document["wheelhouse"])
    wheel = next(house.glob("click-*.whl"))  # uvicorn's transitive dependency
    outcomes = []
    for fault in ("bundle", "wheel-hash", "missing-transitive", "docker", "invalid"):
        original_bundle, original_lock, original_wheel = (
            bundle_file.read_bytes(),
            lock.read_bytes(),
            wheel.read_bytes(),
        )
        changed = {**document, "tag": document["tag"] + "-refused"}
        try:
            if fault == "bundle":
                bundle_file.write_bytes(b"tampered")
            if fault == "wheel-hash":
                wheel.write_bytes(b"tampered")
            if fault == "missing-transitive":
                wheel.unlink()
                lock.write_text(
                    "".join(
                        line
                        for line in original_lock.decode().splitlines(keepends=True)
                        if not line.lower().startswith("click==")
                    )
                )
            if fault == "docker":
                changed["docker"] = {
                    **document["docker"],
                    "executable": "/missing/docker",
                }
            if fault == "invalid":
                changed["tag"] = "--bad-option"
            inputs.write_text(json.dumps(changed))
            command = [
                str(python),
                "-I",
                "-B",
                "-m",
                "apizr.cli",
                "plugins",
                "run",
                "apizr-oci",
                "build",
                "--arguments",
                str(inputs),
                "--plugins-dir",
                str(store),
                "--timeout-ms",
                "360000",
            ]
            result = subprocess.run(
                command, cwd=work, env=environment, capture_output=True, timeout=120
            )
            assert (
                result.returncode == 2
                and result.stdout == b""
                and result.stderr == b"apizr plugins: plugin_failed\n"
            ), (fault, result)
            outcomes.append({"case": fault, "exit_code": result.returncode})
        finally:
            bundle_file.write_bytes(original_bundle)
            lock.write_bytes(original_lock)
            wheel.write_bytes(original_wheel)
    (work / "refusals.json").write_text(json.dumps(outcomes))


def interrupt_build(python, document, store, work, environment):
    """Gate on actual Docker progress, then interrupt the owning core process."""
    marker = work / "docker-started.json"
    wrapper = work / "docker-observer"
    executable = document["docker"]["executable"]
    wrapper.write_text(
        f"#!{sys.executable}\n"
        + f"""import json,os,signal,subprocess,sys
from pathlib import Path
child=subprocess.Popen([{executable!r},*sys.argv[1:]],stderr=subprocess.PIPE)
assert child.stderr is not None
seen=0
while True:
 line=child.stderr.readline(65536)
 if not line: break
 seen+=len(line)
 if seen>1048576: raise SystemExit(2)
 if b'load build definition' in line or b'transferring dockerfile' in line:
  Path({str(marker)!r}).write_text(json.dumps({{'client':child.pid,'cwd':os.getcwd()}}))
  signal.pause()
 sys.stderr.buffer.write(line);sys.stderr.buffer.flush()
raise SystemExit(child.wait())
"""
    )
    wrapper.chmod(0o700)
    changed = {**document, "docker": {**document["docker"], "executable": str(wrapper)}}
    args_file = work / "interrupt-build.json"
    args_file.write_text(json.dumps(changed))
    process = subprocess.Popen(
        [
            str(python),
            "-I",
            "-B",
            "-m",
            "apizr.cli",
            "plugins",
            "run",
            "apizr-oci",
            "build",
            "--arguments",
            str(args_file),
            "--plugins-dir",
            str(store),
            "--timeout-ms",
            "360000",
        ],
        cwd=work,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 30
        while not marker.exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                raise AssertionError("Docker progress handshake absent")
            time.sleep(0.02)
        observed = json.loads(marker.read_text())
        process.send_signal(signal.SIGINT)
        out, err = process.communicate(timeout=5)
        assert (
            process.returncode == 130
            and out == b""
            and err == b"apizr plugins: cancelled\n"
        )
        assert not Path(observed["cwd"]).exists()
        terminal = subprocess.run(
            ["ps", "-p", str(observed["client"]), "-o", "stat="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        assert not terminal.stdout.strip() or terminal.stdout.strip().startswith("Z"), (
            terminal.stdout
        )
        # Do not infer any daemon state from killing the local client.
        (work / "interruption.json").write_text(
            json.dumps(
                {
                    "exit_code": 130,
                    "context_removed": True,
                    "daemon_completion_confirmed": False,
                }
            )
        )
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
        process.communicate(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--base", default="python:3.14-slim")
    parser.add_argument("--buildx", type=Path)
    parser.add_argument("--docker-socket", type=Path, required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    if work.is_relative_to(REPO):
        parser.error("proof must run outside checkout")
    work.mkdir(parents=True, exist_ok=False)
    docker = shutil.which("docker")
    assert docker
    environment = dict(
        os.environ, PYTHONDONTWRITEBYTECODE="1", UV_PYTHON_DOWNLOADS="never"
    )
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    docker_flags = [docker, "--host", "unix://" + str(args.docker_socket)]

    def command(*cmd, **kwargs):
        return run(cmd, cwd=work, env=environment, **kwargs)

    def engine(*cmd):
        return command(*docker_flags, *cmd)

    # Preparation may fetch the explicitly chosen base and server wheels.
    engine("pull", args.base)
    base_info = json.loads(engine("image", "inspect", args.base))[0]
    base = base_info["RepoDigests"][0]
    platform = base_info["Os"] + "/" + base_info["Architecture"]
    house = work / "plugin-wheels"
    house.mkdir()
    command("uv", "build", "--wheel", REPO, "--out-dir", house)
    command("uv", "build", "--wheel", REPO / "plugins/oci", "--out-dir", house)
    core = next(house.glob("outerspace_apizr-*.whl"))
    plugin = next(house.glob("apizr_oci-*.whl"))
    preparation = work / "preparation"
    command("uv", "venv", "--seed", "--python", sys.executable, preparation)
    command(
        preparation / "bin/python",
        "-m",
        "pip",
        "download",
        "--only-binary=:all:",
        "--dest",
        house,
        core,
        plugin,
    )
    plugin_lock = work / "plugin.lock"
    lock_wheels(house, plugin_lock)
    core_env = work / "core"
    command("uv", "venv", "--python", sys.executable, core_env)
    python = core_env / "bin/python"
    command(
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "--offline",
        "--no-index",
        "--find-links",
        house,
        core,
    )

    def cli(*cmd):
        return command(python, "-I", "-B", "-m", "apizr.cli", *cmd)

    inventory = "import importlib.metadata as m,json; print(json.dumps(sorted((d.metadata['Name'],d.version) for d in m.distributions())))"
    before = snapshot(core_env)
    before_distributions = command(python, "-I", "-B", "-c", inventory)
    command(
        python,
        "-I",
        "-B",
        "-c",
        "import importlib.util as u; assert all(u.find_spec(n) is None for n in ('apizr_oci','fastapi','mcp','uvicorn'))",
    )
    store = work / "plugins"
    cli(
        "plugins",
        "install",
        plugin,
        "--sha256",
        hashlib.sha256(plugin.read_bytes()).hexdigest(),
        "--requirements",
        plugin_lock,
        "--wheelhouse",
        house,
        "--plugins-dir",
        store,
    )
    assert not json.loads(
        cli("plugins", "list", "--active", "--json", "--plugins-dir", store)
    )["installations"]
    cli("plugins", "enable", "apizr-oci", "--version", "0.0.0", "--plugins-dir", store)
    # Existing proof: real HTTPS repository, verified TLS, exact commit, four commands.
    old = os.environ.get("PYTHONDONTWRITEBYTECODE")
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        git_bundles(python, core_env / "bin/apizr", work)
    finally:
        if old is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = old
    images = []
    containers = []
    results = []
    try:
        for interface in ("rest", "mcp"):
            bundle = work / "git-proof" / ("remote-" + interface)
            wheels = work / (interface + "-wheels")
            wheels.mkdir()
            # Resolve for the actual target interpreter/platform in a disposable container.
            engine(
                "run",
                "--rm",
                "--platform",
                platform,
                "--mount",
                f"type=bind,src={wheels},dst=/wheels",
                "--mount",
                f"type=bind,src={bundle / 'requirements.txt'},dst=/requirements.txt,readonly",
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
            requirements = work / (interface + ".lock")
            lock_wheels(wheels, requirements)
            tag = "apizr-oci-proof:" + interface + "-" + uuid.uuid4().hex[:12]
            images.append(tag)
            document = {
                "schema": "apizr.oci-build/v1",
                "bundle": str(bundle),
                "interface": interface,
                "base_image": base,
                "platform": platform,
                "tag": tag,
                "requirements": str(requirements),
                "wheelhouse": str(wheels),
                "docker": {
                    "executable": docker,
                    "socket": str(args.docker_socket),
                    "buildx": str(args.buildx.resolve()) if args.buildx else None,
                },
                "timeout_ms": 300000,
                "max_log_bytes": 1048576,
            }
            build_json = work / (interface + "-build.json")
            build_json.write_text(json.dumps(document, indent=2) + "\n")
            if interface == "rest":
                refuse_builds(python, document, store, work, environment)
                cancelled_tag = tag + "-interrupted"
                images.append(cancelled_tag)
                interrupt_build(
                    python, {**document, "tag": cancelled_tag}, store, work, environment
                )
            result = json.loads(
                cli(
                    "plugins",
                    "run",
                    "apizr-oci",
                    "build",
                    "--arguments",
                    build_json,
                    "--timeout-ms",
                    "360000",
                    "--plugins-dir",
                    store,
                )
            )
            assert result["status"] == "ok" and result["result"]["published"] is False
            inspect = json.loads(engine("image", "inspect", tag))[0]
            assert inspect["Id"] == result["result"]["image_id"]
            assert inspect["Config"]["User"] == "65532:65532"
            assert not inspect["Config"].get("Volumes")
            results.append(result)
        shutil.rmtree(work / "git-proof")
        assert not (work / "git-proof").exists()
        # REST can be called after both source and bundle have gone.
        container = engine("run", "--detach", "--publish", "127.0.0.1::8000", images[0])
        containers.append(container)
        address = engine("port", container, "8000/tcp").splitlines()[0]
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(
                    "http://" + address + "/health", timeout=1
                ) as response:
                    assert json.load(response) == {"status": "ok"}
                break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        request = urllib.request.Request(
            "http://" + address + "/capabilities/calculator.add",
            data=b'{"a":2,"b":3}',
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.load(response) == 5
        # MCP client remains outside the minimal core and talks through docker stdio.
        mcp_client = work / "mcp-client"
        command("uv", "venv", "--python", sys.executable, mcp_client)
        command(
            "uv", "pip", "install", "--python", mcp_client / "bin/python", "mcp>=2.2,<3"
        )
        name = "apizr-mcp-proof-" + uuid.uuid4().hex[:12]
        containers.append(name)
        command(
            mcp_client / "bin/python",
            "-I",
            "-c",
            """import asyncio, sys
from mcp import Client, StdioServerParameters
async def check():
    async with Client(StdioServerParameters(command=sys.argv[1], args=['--host',sys.argv[2],'run','--rm','--interactive','--name',sys.argv[3],sys.argv[4]],env={})) as client:
        assert [t.name for t in (await client.list_tools()).tools] == ['calculator.add']
        result = await client.call_tool('calculator.add', {'a':2,'b':3})
        assert not result.is_error and result.structured_content == 5
asyncio.run(check())
""",
            docker,
            "unix://" + str(args.docker_socket),
            name,
            results[1]["result"]["tag"],
            timeout=45,
        )
        assert snapshot(core_env) == before
        assert command(python, "-I", "-B", "-c", inventory) == before_distributions
        (work / "results.json").write_text(json.dumps(results, indent=2))
        print(
            "PASS Git -> installed/activated plugin -> real REST/MCP images -> sources removed -> successful calls; core unchanged",
            flush=True,
        )
    finally:
        for container in containers:
            subprocess.run(
                [*docker_flags, "rm", "--force", container],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
        for tag in images:
            subprocess.run(
                [*docker_flags, "image", "rm", tag],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )


if __name__ == "__main__":
    main()
