"""Run the documented notebook journey from retained candidate/science wheels."""

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from email.parser import BytesParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/data-science/fraud-detection"
GUIDE = ROOT / "docs/getting-started/data-science.md"
PACKAGES = ("outerspace-apizr", "pandas", "numpy", "scipy", "scikit-learn", "joblib")
PAYLOAD = {
    "transaction": {
        "amount": 845.0,
        "transaction_velocity": 11,
        "foreign_transaction": True,
        "account_age_days": 45,
    }
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def run(arguments, *, cwd, env=None, timeout=180):
    result = subprocess.run(
        list(map(str, arguments)),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"{arguments}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def network_guard(python, log):
    """Qualification instrumentation in site-packages survives worker -I/clean env.

    It guards this non-adversarial Python workload, not arbitrary hostile native
    code. Loopback REST/MCP remains permitted; DNS and external socket operations
    raise before network access. No product source is modified.
    """
    site = Path(
        run(
            [
                python,
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            cwd=log.parent,
        ).strip()
    )
    (site / "qualification_network_guard.py").write_text(
        """import ipaddress, os, socket, sys
from pathlib import Path
LOG = Path("""
        + repr(str(log))
        + """)
def record(event):
    with LOG.open("a") as stream:
        stream.write(str(os.getpid()) + " " + event + "\\n")
def host(value):
    if isinstance(value, bytes): value = value.decode("ascii")
    if value == "localhost": return True
    try: return ipaddress.ip_address(value).is_loopback
    except ValueError: return False
def audit(event, args):
    address = None
    if event in {"socket.connect", "socket.bind"}:
        address = args[1]
    elif event == "socket.sendto":
        address = args[-1]
    elif event == "socket.getaddrinfo":
        address = (args[0], args[1])
    elif event == "cpython.run_module":
        record("module " + str(args[0]))
    if isinstance(address, tuple) and not host(address[0]):
        record("denied " + event)
        raise PermissionError("qualification_external_network_denied")
sys.addaudithook(audit)
record("guard installed")
"""
    )
    (site / "qualification_network_guard.pth").write_text(
        "import qualification_network_guard\n"
    )
    probe = """import socket
try: socket.create_connection(("192.0.2.1",443),timeout=1)
except PermissionError as error: assert str(error)=="qualification_external_network_denied"
else: raise AssertionError("external network was not guarded")
"""
    run([python, "-I", "-c", probe], cwd=log.parent, env={})


def blocks():
    return dict(
        re.findall(
            r"<!-- science:([a-z-]+) -->\s*```sh\n(.*?)\n```", GUIDE.read_text(), re.S
        )
    )


def journey(python, project, wheelhouse, target, output, *, serving_python):
    """Consume the public notebook and exact command blocks, without checkout imports."""
    activated = time.monotonic()
    python, project, output = python.absolute(), project.resolve(), output.resolve()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    env.update(
        PATH=str(python.parent) + os.pathsep + os.environ["PATH"],
        SCIENCE_WHEELHOUSE=str(wheelhouse.resolve()),
        TARGET=str(target.resolve()),
        BUNDLES=str(output / "bundles"),
        SERVING_PYTHON=str(serving_python.absolute()),
        CAPABILITY="python:fraud_detection:predict",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        env["REST_PORT"] = str(listener.getsockname()[1])
    imported = json.loads(
        run(
            [
                python,
                "-I",
                "-c",
                "import apizr,json,sys; from importlib.metadata import version; print(json.dumps({'path':apizr.__file__,'python':sys.version.split()[0],'packages':{n:version(n) for n in sys.argv[1:]}}))",
                *PACKAGES,
            ],
            cwd=output,
            env=env,
        )
    )
    assert imported["packages"]["outerspace-apizr"] == "0.4.5"
    assert Path(imported["path"]).is_relative_to(python.parent.parent)
    assert not Path(imported["path"]).is_relative_to(ROOT)
    notebook = project / "fraud_detection.ipynb"
    raw = notebook.read_bytes()
    source = "\n".join(
        "".join(c["source"])
        for c in json.loads(raw)["cells"]
        if c["cell_type"] == "code"
    )
    assert not any(
        isinstance(n, (ast.Import, ast.ImportFrom))
        and "apizr" in ast.unparse(n).lower()
        for n in ast.walk(ast.parse(source))
    )
    assert "apizr" not in source.lower()
    assert not (project / "artifacts").exists()
    run(
        [
            python,
            "-I",
            "-c",
            "import nbformat,sys; nbformat.validate(nbformat.read(sys.argv[1],as_version=4))",
            notebook,
        ],
        cwd=output,
        env=env,
    )
    stages, timings, identities = blocks(), {}, {}

    def unchanged(stage):
        assert notebook.read_bytes() == raw
        identities[stage] = digest(notebook)

    def stage(name):
        started = time.monotonic()
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", stages[name]],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        timings[name] = time.monotonic() - started
        (output / (name + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(
                f"Documented stage {name}: {result.stdout}\n{result.stderr}"
            )
        unchanged(name)
        return result.stdout

    def command(*arguments, expected=0):
        result = subprocess.run(
            [str(python), "-I", "-m", "apizr.cli", "experiment", *map(str, arguments)],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return result

    started = time.monotonic()
    inspection_text = stage("inspect")
    excerpt = re.search(
        r"Excerpt from the reference notebook's inspection:\s*```text\n(.*?)\n```",
        GUIDE.read_text(),
        re.S,
    )
    assert excerpt and excerpt.group(1) in inspection_text
    first_value = time.monotonic() - activated
    assert not (project / "artifacts").exists()
    inspection = json.loads(
        command("inspect", notebook.name, "--format", "json").stdout
    )
    assert set(inspection["states"]) == {
        "code",
        "data",
        "parameters",
        "randomness",
        "environment",
        "metrics",
        "outputs",
        "serving",
    }
    write(output / "inspection-a.json", inspection)
    stage("run-a")
    a = json.loads((project / "run-a.json").read_text())
    assert a["status"] == "success" and a["metrics"] == 3
    assert (project / "artifacts/trained.txt").is_file()
    env["RUN_A"] = a["run_digest"]
    record_a = json.loads(command("show", env["RUN_A"], "--format", "json").stdout)
    write(output / "run-a.json", record_a)
    before = {
        p.relative_to(project).as_posix(): digest(p)
        for p in project.rglob("*")
        if p.is_file()
    }
    stage("run-b")
    after = {
        p.relative_to(project).as_posix(): digest(p)
        for p in project.rglob("*")
        if p.is_file()
    }
    changed = sorted(
        name
        for name in before.keys() | after.keys()
        if before.get(name) != after.get(name)
    )
    assert all(
        name in {"data/transactions.csv", "artifacts/model.joblib", "run-b.json"}
        or name.startswith(".apizr/")
        for name in changed
    ), changed
    b = json.loads((project / "run-b.json").read_text())
    assert b["status"] == "success" and b["metrics"] == 3
    env["RUN_B"] = b["run_digest"]
    record_b = json.loads(command("show", env["RUN_B"], "--format", "json").stdout)
    write(output / "run-b.json", record_b)
    for key in ("subject", "parameters", "randomness", "environment"):
        assert record_a["plan"][key] == record_b["plan"][key], key
    assert (
        record_a["run"]["effective_parameters"]
        == record_b["run"]["effective_parameters"]
    )
    assert (
        record_a["plan"]["inputs"][0]["digest"]
        != record_b["plan"]["inputs"][0]["digest"]
    )
    assert record_a["run"]["metrics"] != record_b["run"]["metrics"]
    models = [
        next(o for o in record["run"]["outputs"] if o["name"] == "model")
        for record in (record_a, record_b)
    ]
    assert (
        models[0]["digest"]
        != models[1]["digest"]
        == digest(project / "artifacts/model.joblib")
    )
    stage("list")
    history = json.loads(command("list", "--format", "json").stdout)
    assert {r["run_digest"] for r in history["runs"]} == {env["RUN_A"], env["RUN_B"]}
    stage("show")
    stage("diff")
    comparison = json.loads(
        command("diff", env["RUN_A"], env["RUN_B"], "--format", "json").stdout
    )
    assert comparison["data"][0]["content_state"] == "changed"
    assert any(m["state"] == "changed" for m in comparison["metrics"])
    write(output / "diff.json", comparison)
    stage("authority")
    stage("rest-expose")
    stage("rest-install")
    network_guard(serving_python, output / "network.log")
    stage("rest-start")
    try:
        rest = json.loads(stage("rest-call"))
        label, probability = rest["predictions"][0]
        assert 0 <= probability <= 1 and label == int(probability >= 0.5)
        stage("mcp-expose")
        mcp = json.loads(stage("mcp-call"))
        assert mcp == rest
        total = time.monotonic() - started
        write(output / "transport.json", {"request": PAYLOAD, "rest": rest, "mcp": mcp})
        url = "http://127.0.0.1:" + env["REST_PORT"]
        with urlopen(url + "/openapi.json", timeout=10) as response:
            paths = json.load(response)["paths"]
        assert [p for p, methods in paths.items() if "post" in methods] == [
            "/capabilities/fraud_detection.predict"
        ]
        invalid = [dict(PAYLOAD["transaction"]) for _ in range(3)]
        del invalid[0]["amount"]
        invalid[1]["amount"] = "845.0"
        invalid[2]["extra"] = True
        for value in invalid:
            try:
                urlopen(
                    Request(
                        url + "/capabilities/fraud_detection.predict",
                        data=json.dumps({"transaction": value}).encode(),
                        headers={"Content-Type": "application/json"},
                    ),
                    timeout=10,
                )
            except HTTPError as error:
                assert error.code in {400, 422}
            else:
                raise AssertionError("TypedDict invalid REST input accepted")
    finally:
        pidfile = output / "bundles/rest.pid"
        if pidfile.exists():
            os.kill(int(pidfile.read_text()), 15)
    assert not (output / "bundles/rest/source/artifacts/trained.txt").exists()
    assert (output / "bundles/rest/source/features.py").is_file()
    common = [
        "--root",
        ".",
        "--operator-policy",
        "operator.json",
        "--capability",
        env["CAPABILITY"],
        "--interface",
        "rest",
        "--artifact",
        "model",
        "--dependency",
        "joblib",
        "--dependency",
        "scikit-learn",
        "--dependency-wheelhouse",
        str(wheelhouse),
        "--allow-conditional",
    ]
    stale = command(
        "expose", env["RUN_A"], *common, "--output-dir", output / "stale", expected=2
    )
    assert not (output / "stale").exists()
    (output / "stale.log").write_text(stale.stderr)
    assert "apizr.experiments.worker" in (output / "network.log").read_text()
    unchanged("completed")
    result = {
        "status": "passed",
        "runtime": imported,
        "timings_seconds": timings,
        "journey_seconds": total,
        "time_to_first_value_seconds": first_value,
        "source_hashes": identities,
        "run_a": a,
        "run_b": b,
        "data_a": digest(project / "data/transactions-a.csv"),
        "data_b": digest(project / "data/transactions-b.csv"),
        "changed_files": changed,
        "rest_mcp_parity": True,
        "rest_typeddict_refusals": 3,
        "stale_model_refused": True,
        "inspection_did_not_execute": True,
        "offline_python_guard": True,
    }
    write(output / "journey.json", result)
    return result


def serving_checks(python, serving, bundles, output):
    """Independent real clients, invalid TypedDict inputs and measured startup/calls."""
    script = r"""
import json, os, socket, subprocess, sys, time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import anyio
from mcp import Client, StdioServerParameters
serving, bundles, output = map(Path, sys.argv[1:])
payload = {"transaction": {"amount": 845.0, "transaction_velocity": 11,
                           "foreign_transaction": True, "account_age_days": 45}}
invalid = [dict(payload["transaction"]) for _ in range(3)]
del invalid[0]["amount"]
invalid[1]["amount"] = "845.0"
invalid[2]["extra"] = True
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
times = {}
with (output / "standalone-rest.log").open("w") as log:
    started = time.monotonic()
    server = subprocess.Popen([str(serving), "-I", "-c",
        "import sys; sys.path.insert(0,sys.argv[1]); from app import app; import uvicorn; assert not any(n=='apizr' or n.startswith('apizr.') for n in sys.modules); uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='error')",
        str(bundles / "rest"), str(port)], cwd=output, stdout=log, stderr=log)
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                with urlopen(base + "/health", timeout=1) as response:
                    assert json.load(response) == {"status":"ok"}
                break
            except OSError:
                if time.monotonic() >= deadline or server.poll() is not None: raise
                time.sleep(.05)
        times["rest_startup"] = time.monotonic() - started
        started = time.monotonic()
        with urlopen(Request(base + "/capabilities/fraud_detection.predict",
                             data=json.dumps(payload).encode(),
                             headers={"Content-Type":"application/json"}), timeout=20) as response:
            rest = json.load(response)
        times["rest_call"] = time.monotonic() - started
    finally:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=10)
async def main():
    started = time.monotonic()
    async with Client(StdioServerParameters(command=str(serving),
                      args=[str(bundles / "mcp/server.py")], cwd=output), read_timeout_seconds=20) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools.tools] == ["fraud_detection.predict"]
        times["mcp_startup_and_list"] = time.monotonic() - started
        started = time.monotonic()
        result = await client.call_tool("fraud_detection.predict", payload)
        times["mcp_call"] = time.monotonic() - started
        assert not result.is_error and result.structured_content == rest
        for bad in invalid:
            result = await client.call_tool("fraud_detection.predict", {"transaction": bad})
            assert result.is_error
        return {"tools": [tool.name for tool in tools.tools], "structuredContent": rest,
                "invalid_typeddict_requests_refused": len(invalid)}
result = anyio.run(main)
result.update(rest=rest, timings_seconds=times)
print(json.dumps(result))
"""
    result = json.loads(
        run([python, "-I", "-c", script, serving, bundles, output], cwd=output)
    )
    write(output / "standalone-transports.json", result)
    return result


def retained_reproduction(
    python, second, serving, project, wheels, target, output, install
):
    """Fresh installation, fixed-evidence replay, private helpers and scoped refusals."""
    setup = time.monotonic()
    run([python, "-m", "venv", second.parent.parent], cwd=output)
    install = [str(second), *map(str, install[1:])]
    (output / "second-install.log").write_text(run(install, cwd=output))
    network_guard(second, output / "network.log")
    setup = time.monotonic() - setup
    copied = output / "reproduction"
    shutil.copytree(project, copied)
    authority = {
        "schema": "apizr.operator-policy/v1",
        "grants": [
            {
                "adapter": "repository",
                "operation": "analyze",
                "target": {"kind": "local", "root": str(copied)},
                "permissions": ["source.analyze"],
            }
        ],
    }
    write(copied / "operator.json", authority)
    run_b = json.loads((project / "run-b.json").read_text())["run_digest"]
    args = [
        "expose",
        run_b,
        "--root",
        ".",
        "--operator-policy",
        "operator.json",
        "--capability",
        "python:fraud_detection:predict",
        "--artifact",
        "model",
        "--dependency",
        "joblib",
        "--dependency",
        "scikit-learn",
        "--dependency-wheelhouse",
        wheels,
        "--allow-conditional",
    ]

    def cli(*arguments, expected=0):
        proc = subprocess.run(
            [str(second), "-I", "-m", "apizr.cli", "experiment", *map(str, arguments)],
            cwd=copied,
            capture_output=True,
            text=True,
            timeout=90,
            env={
                k: v
                for k, v in os.environ.items()
                if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
            },
        )
        assert proc.returncode == expected, proc.stdout + proc.stderr
        return proc

    hashes = {}
    for interface in ("rest", "mcp"):
        replay = output / "replayed-bundles" / interface
        cli(*args, "--interface", interface, "--output-dir", replay)

        def tree(root):
            return {
                p.relative_to(root).as_posix(): digest(p)
                for p in root.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts
            }

        original = tree(output / "bundles" / interface)
        assert original == tree(replay)
        hashes[interface] = original
    write(output / "replayed-bundle-hashes.json", hashes)
    shutil.copyfile(
        copied / "data/transactions-a.csv", copied / "data/transactions.csv"
    )
    inspection = json.loads(
        cli("inspect", "fraud_detection.ipynb", "--format", "json").stdout
    )
    assert inspection == json.loads((output / "inspection-a.json").read_text())
    again = json.loads(
        cli(
            "run",
            "fraud_detection.ipynb",
            "--output",
            "model=artifacts/model.joblib",
            "--format",
            "json",
        ).stdout
    )
    original_a = json.loads((project / "run-a.json").read_text())
    assert (
        again["status"] == "success"
        and again["plan_digest"] == original_a["plan_digest"]
    )
    assert again["run_digest"] != original_a["run_digest"]
    # Restore B's exact retained bytes for fixed-Run slice qualifications.
    shutil.copyfile(project / "data/transactions.csv", copied / "data/transactions.csv")
    shutil.copyfile(
        project / "artifacts/model.joblib", copied / "artifacts/model.joblib"
    )
    (copied / "unfinished.py").write_text(
        "from contextlib import contextmanager\n@contextmanager\ndef events():\n    yield 1\n"
    )
    (copied / "unused.py").write_text(
        "from unfinished import events\ndef research(): return None\n"
    )
    ambiguous = output / "unfinished-repository"
    cli(*args, "--interface", "rest", "--output-dir", ambiguous)
    graph = json.loads((ambiguous / "capability-graph.json").read_text())
    assert not graph["complete"] and any(
        d["path"] == "unused.py" for d in graph["diagnostics"]
    )
    assert (ambiguous / "source/unfinished.py").is_file()
    assert (ambiguous / "source/features.py").is_file()
    helper = copied / "features.py"
    helper.write_text(
        helper.read_text()
        + "\nraise RuntimeError('required helper initialization is unsafe')\n"
    )
    refused = cli(
        *args,
        "--interface",
        "rest",
        "--output-dir",
        output / "unsafe-helper",
        expected=1,
    )
    assert "features.py" in refused.stderr and not (output / "unsafe-helper").exists()
    (output / "unsafe-helper.log").write_text(refused.stderr)
    # Serving must work without either source tree or their local Run stores.
    project.rename(project.with_name("removed-project"))
    copied.rename(output / "removed-reproduction")
    bundle_copy = output / "standalone-bundles"
    shutil.copytree(output / "bundles", bundle_copy)
    run(
        [
            serving,
            "-I",
            "-c",
            "from importlib.util import find_spec; assert find_spec('apizr') is None; assert find_spec('pandas') is None",
        ],
        cwd=output,
    )
    transport = serving_checks(python, serving, bundle_copy, output)
    result = {
        "second_setup_seconds": setup,
        "same_inspection": True,
        "same_plan": True,
        "second_run": again,
        "fixed_run_bundle_bytes_identical": True,
        "unrelated_ambiguity_retained": True,
        "required_helper_defect_refused": True,
        "without_original_projects": True,
        "serving_without_apizr_or_pandas": True,
        "transports": transport,
    }
    write(output / "reproduction.json", result)
    return result


def scientific_inventory(wheels, output):
    inventory = []
    for wheel in sorted(wheels.glob("*.whl")):
        with zipfile.ZipFile(wheel) as archive:
            metadata = BytesParser().parsebytes(
                archive.read(
                    next(
                        name
                        for name in archive.namelist()
                        if name.endswith(".dist-info/METADATA")
                    )
                )
            )
            expression = metadata.get("License-Expression")
            classifiers = [
                str(c)
                for c in metadata.get_all("Classifier", [])
                if c.startswith("License ::")
            ]
            license_text = metadata.get("License")
            assert expression or classifiers or license_text, wheel.name
            inventory.append(
                {
                    "name": str(metadata["Name"]),
                    "version": str(metadata["Version"]),
                    "filename": wheel.name,
                    "sha256": digest(wheel),
                    "license_expression": str(expression) if expression else None,
                    "license_classifiers": classifiers,
                    "license_declaration": str(license_text) if license_text else None,
                }
            )
    write(
        output / "science-wheels.json",
        {
            "python": sys.version.split()[0],
            "platform": platform.system(),
            "architecture": platform.machine(),
            "wheels": inventory,
            "license_status": "declarations recorded from retained wheels",
        },
    )
    return inventory


def main():
    from coordinated_distributions import load

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--primary",
        action="store_true",
        help="Enforce the five-minute target on the primary reference host",
    )
    args = parser.parse_args()
    args.candidate = args.candidate.resolve()
    args.target = args.target.resolve()
    candidate = load(args.candidate)
    assert candidate["version"] == "0.4.5"
    output = args.output.resolve()
    assert not output.exists() and not output.is_relative_to(ROOT)
    output.mkdir(parents=True)
    work = output / "work"
    work.mkdir()
    project = work / "project"
    shutil.copytree(EXAMPLE, project)
    shutil.copyfile(
        project / "data/transactions-a.csv", project / "data/transactions.csv"
    )
    started = time.monotonic()
    python = work / "science/bin/python"
    serving = work / "serving/bin/python"
    for environment in (python.parent.parent, serving.parent.parent):
        run([sys.executable, "-m", "venv", environment], cwd=work)
    generated = work / "generated-data"
    generated.mkdir()
    shutil.copyfile(EXAMPLE / "generate_data.py", generated / "generate_data.py")
    run([python, "-I", generated / "generate_data.py"], cwd=generated)
    assert all(
        (generated / "data" / name).read_bytes()
        == (EXAMPLE / "data" / name).read_bytes()
        for name in ("transactions-a.csv", "transactions-b.csv")
    )
    wheels = output / "science-wheels"
    download_started = time.monotonic()
    download = run(
        [
            python,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--dest",
            wheels,
            "-r",
            EXAMPLE / "requirements.txt",
        ],
        cwd=work,
    )
    (output / "science-download.log").write_text(download)
    download_seconds = time.monotonic() - download_started
    install = [
        python,
        "-m",
        "pip",
        "install",
        "--no-index",
        "--find-links",
        args.target / "base",
        "--find-links",
        args.target / "extras",
        "--find-links",
        wheels,
        str(args.candidate.resolve() / "dist/outerspace_apizr-0.4.5-py3-none-any.whl")
        + "[notebook,http,mcp]",
        "-r",
        EXAMPLE / "requirements.txt",
    ]
    install_started = time.monotonic()
    (output / "install.log").write_text(run(install, cwd=work))
    install_seconds = time.monotonic() - install_started
    setup = time.monotonic() - started
    inventory = scientific_inventory(wheels, output)
    audit_requirements = output / "science-audit-requirements.txt"
    audit_requirements.write_text(
        "".join(
            f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n"
            for item in inventory
        )
    )
    audit = run(
        [
            "uv",
            "run",
            "--locked",
            "--group",
            "security",
            "pip-audit",
            "--no-deps",
            "--disable-pip",
            "-r",
            audit_requirements,
            "--format",
            "json",
            "--output",
            output / "science-audit.json",
        ],
        cwd=ROOT,
    )
    (output / "science-audit.log").write_text(audit)
    audited = json.loads((output / "science-audit.json").read_text())
    assert len(audited["dependencies"]) == len(inventory)
    assert all(not package["vulns"] for package in audited["dependencies"])
    network_guard(python, output / "network.log")
    network_guard(serving, output / "network.log")
    result = journey(
        python, project, wheels, args.target, output, serving_python=serving
    )
    result["reproduction"] = retained_reproduction(
        python,
        work / "second/bin/python",
        serving,
        project,
        wheels,
        args.target,
        output,
        install,
    )
    if args.primary:
        assert result["journey_seconds"] <= 300, result["journey_seconds"]
    result.update(
        candidate_commit=candidate["commit"],
        candidate_manifest_sha256=digest(args.candidate / "candidate.json"),
        setup_seconds=setup,
        download_seconds=download_seconds,
        install_seconds=install_seconds,
        synthetic_data_reproduced=True,
    )
    write(output / "journey.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
