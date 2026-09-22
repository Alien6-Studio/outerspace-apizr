"""Validate a built wheel and exercise its installed CLI outside the checkout."""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--runtime-image-config", type=Path, help="Explicit local OCI test image JSON"
    )
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "apizr/__init__.py" in names
        assert "apizr/capabilities/model.py" in names
        assert "apizr/readiness/model.py" in names
        assert "apizr/generators/rest/runtime.py" in names
        assert "apizr/generators/rest/templates/preamble.txt" in names
        assert "apizr/exposure/planner.py" in names
        assert "apizr/exposure_cli.py" in names
        assert "apizr/interfaces/runtime.py" in names
        assert "apizr/generators/mcp/runtime.py" in names
        assert not any(name == "src.py" or name.startswith("src/") for name in names)
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in names)
        assert "apizr/modules/fast_apizr/generator/templates/fastApiApp.j2" in names
        assert "apizr/i18n/en/messages.json" in names
    notebook = Path(__file__).resolve().parents[1] / "examples/pricing.ipynb"
    with tempfile.TemporaryDirectory(prefix="apizr-wheel-") as directory:
        root = Path(directory).resolve()
        env = root / "env"
        subprocess.run(["uv", "venv", "--python", args.python, str(env)], check=True)
        bin_dir = env / ("Scripts" if sys.platform == "win32" else "bin")
        python = bin_dir / "python"
        cli = bin_dir / "apizr"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel) + "[legacy]"],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                """import apizr, importlib.util
from apizr.capabilities import inspect_source, canonical_bytes, document_digest
assert apizr.__file__
assert importlib.util.find_spec('src') is None
ir = inspect_source(b'def work(x: int) -> int: return x', module_name='installed')
assert ir.schema_version == 'apizr.capability/v1'
assert ir.capabilities[0].id == 'python:installed:work'
assert canonical_bytes(ir).endswith(b'\\n')
assert len(document_digest(ir).value) == 64
print(apizr.__file__)
""",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [str(cli), "--help"], cwd=root, check=True, stdout=subprocess.DEVNULL
        )
        version_result = subprocess.run(
            [str(cli), "--version"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        expected_version = subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "from importlib.metadata import version; print('outerspace-apizr ' + version('outerspace-apizr'))",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        assert version_result.stdout == expected_version.stdout
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("smoke_readme.py").resolve()),
                str(cli),
            ],
            cwd=root,
            check=True,
        )
        # Both inputs live outside the repository; the installed CLI must be sufficient.
        source = root / "sample.py"
        source.write_text("def total(values: list[int]) -> int: return sum(values)\n")
        complex_root = root / "complex-notebook"
        shutil.copytree(notebook.parent / "complex-notebook", complex_root)
        complex_output = root / "complex-output"
        subprocess.run(
            [
                str(cli),
                "--notebook",
                str(complex_root / "pricing.ipynb"),
                "--configuration",
                str(complex_root / "configuration.yaml"),
                "--output-dir",
                str(complex_output),
            ],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        assert (complex_output / "data/prices.json").read_bytes() == (
            complex_root / "data/prices.json"
        ).read_bytes()
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import sys; sys.path.insert(0, sys.argv[1]); from pricing import quote; assert quote('coffee', 2) == 7.0",
                str(complex_output),
            ],
            cwd=root,
            check=True,
        )
        local_notebook = root / "sample.ipynb"
        local_notebook.write_text(
            json.dumps(
                {
                    "nbformat": 4,
                    "nbformat_minor": 5,
                    "metadata": {},
                    "cells": [
                        {
                            "cell_type": "code",
                            "id": "sample",
                            "metadata": {},
                            "execution_count": None,
                            "outputs": [],
                            "source": source.read_text(),
                        }
                    ],
                }
            )
        )
        # Repository scanning uses only installed resources, outside the checkout.
        scan_root = root / "scan-project"
        scan_source = scan_root / "src" / "pricing.py"
        scan_source.parent.mkdir(parents=True)
        scan_source.write_text(
            "def total(values: list[int]) -> int: return sum(values)\n"
        )
        scanned = subprocess.run(
            [str(cli), "scan", str(scan_root), "--source-root", "src", "--catalog"],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=20,
        )
        catalog = json.loads(scanned.stdout)
        assert catalog["schema_version"] == "apizr.catalog/v1"
        assert catalog["capabilities"][0]["id"] == "python:pricing:total"
        assert catalog["sources"][0]["path"] == "src/pricing.py"
        assert str(root).encode() not in scanned.stdout
        subprocess.run(
            [str(cli), "scan", str(scan_root), "--source-root", "src"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        (scan_source.parent / "checkout.py").write_text(
            "from pricing import total\ndef checkout(values: list[int]) -> int: return total(values)\n"
        )
        graphed = subprocess.run(
            [str(cli), "graph", str(scan_root), "--source-root", "src", "--graph"],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=20,
        )
        graph = json.loads(graphed.stdout)
        assert graph["schema_version"] == "apizr.graph/v1"
        assert any(
            edge["kind"] == "calls_capability"
            and edge["source"] == "python:checkout:checkout"
            and edge["target"] == "python:pricing:total"
            for edge in graph["relationships"]
        )
        assert str(root).encode() not in graphed.stdout
        subprocess.run(
            [str(cli), "graph", str(scan_root), "--source-root", "src"],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        # Readiness consumes one discovery, or independently persisted matching
        # artifacts; both installed entry points must emit exactly the same bytes.
        scanned_after_graph = subprocess.run(
            [str(cli), "scan", str(scan_root), "--source-root", "src", "--catalog"],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=20,
        )
        catalog_path, graph_path = root / "catalog.json", root / "graph.json"
        catalog_path.write_bytes(scanned_after_graph.stdout)
        graph_path.write_bytes(graphed.stdout)
        readiness_policy = root / "readiness-policy.json"
        for controls in [
            None,
            [],
            ["network_deny", "memory_limit", "cpu_limit", "pid_limit"],
            ["subprocess_deny"],
        ]:
            flags = []
            if controls is not None:
                readiness_policy.write_text(
                    json.dumps(
                        {
                            "execution": {
                                "modes": ["direct", "local-process", "oci-container"],
                                "require_controls": controls,
                            }
                        }
                    )
                )
                flags = ["--policy", str(readiness_policy)]
            repo_report = subprocess.run(
                [
                    str(cli),
                    "readiness",
                    str(scan_root),
                    "--source-root",
                    "src",
                    "--report",
                    *flags,
                ],
                cwd=root,
                capture_output=True,
                timeout=20,
            )
            artifact_report = subprocess.run(
                [
                    str(cli),
                    "repository-readiness",
                    str(catalog_path),
                    str(graph_path),
                    "--format",
                    "json",
                    *flags,
                ],
                cwd=root,
                capture_output=True,
                timeout=20,
            )
            # Checkout's local dependency remains conditional under these policies.
            assert repo_report.returncode == artifact_report.returncode == 1
            assert repo_report.stdout == artifact_report.stdout
            readiness = json.loads(repo_report.stdout)
            assert readiness["schema_version"] == "apizr.repository-readiness/v1"
            assert all(
                mode["runtime_availability"] == "not_assessed"
                for mode in readiness["execution"]
            )
            assert str(root).encode() not in repo_report.stdout
        print(
            "Installed scan/graph/repo-first/artifact-first readiness parity passed outside checkout."
        )
        exposed = subprocess.run(
            [
                str(cli),
                "expose",
                "plan",
                str(scan_root),
                "--source-root",
                "src",
                "--interface",
                "mcp",
                "--execution-mode",
                "oci-container",
                "--select",
                "python:pricing:total",
                "--plan",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=20,
        )
        exposure = json.loads(exposed.stdout)
        assert exposure["schema_version"] == "apizr.exposure-plan/v1"
        assert [c["capability_id"] for c in exposure["capabilities"]] == [
            "python:pricing:total"
        ]
        assert exposure["capabilities"][0]["compatible_execution_modes"] == [
            "oci-container"
        ]
        assert str(root).encode() not in exposed.stdout
        refused = subprocess.run(
            [
                str(cli),
                "expose",
                "plan",
                str(scan_root),
                "--source-root",
                "src",
                "--interface",
                "mcp",
                "--execution-mode",
                "oci-container",
                "--select",
                "python:pricing:typo",
                "--plan",
            ],
            cwd=root,
            capture_output=True,
            timeout=20,
        )
        assert refused.returncode == 1 and not refused.stdout
        print("Installed exposure plan/refusal passed outside checkout.")
        policy = root / "policy.json"
        policy.write_text("{}")
        arguments = root / "arguments.json"
        arguments.write_text('{"values":[1,2]}')
        for target in (source, local_notebook):
            executed = subprocess.run(
                [
                    str(cli),
                    "execute",
                    str(target),
                    "total",
                    "--module-name",
                    "installed.sample",
                    "--arguments",
                    str(arguments),
                    "--policy",
                    str(policy),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=20,
            )
            outcome = json.loads(executed.stdout)
            assert outcome["status"] == "success" and outcome["value"] == 3
            command = [
                str(cli),
                "inspect",
                str(target),
                "--module-name",
                "installed.sample",
            ]
            inspected = subprocess.run(
                command + ["--format", "json"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            report = json.loads(inspected.stdout)
            assert report["schema_version"] == "apizr.inspection/v1"
            assert report["readiness"]["policy_version"] == "apizr.readiness/v1"
            assessment = report["readiness"]["assessments"][0]
            assert (
                assessment["state"] == "ready" and assessment["can_generate_interface"]
            )
            canonical = subprocess.run(
                command + ["--ir"], cwd=root, check=True, capture_output=True
            )
            assert json.loads(canonical.stdout) == report["capability_ir"]
            text = subprocess.run(
                command, cwd=root, check=True, capture_output=True, text=True
            )
            assert "readiness: READY" in text.stdout
            rest_output = root / (
                "rest-notebook" if target.suffix == ".ipynb" else "rest-python"
            )
            subprocess.run(
                [
                    str(cli),
                    "generate",
                    "rest",
                    str(target),
                    "--module-name",
                    "installed.sample",
                    "--output-dir",
                    str(rest_output),
                ],
                cwd=root,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-c",
                    """import asyncio, importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('generated_adapter', root / 'app.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
assert not any(name == 'apizr' or name.startswith('apizr.') for name in sys.modules)
async def check():
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': b'{"values":[1,2]}', 'more_body': False}
    async def send(message):
        messages.append(message)
    await adapter.app({'type':'http', 'asgi':{'version':'3.0'}, 'http_version':'1.1',
        'method':'POST', 'scheme':'http', 'path':'/capabilities/total',
        'raw_path':b'/capabilities/total', 'query_string':b'',
        'headers':[(b'content-type',b'application/json')], 'root_path':'',
        'client':('127.0.0.1', 1), 'server':('localhost',80)}, receive, send)
    assert messages[0]['status'] == 200, messages
    assert json.loads(b''.join(m.get('body',b'') for m in messages)) == 3
asyncio.run(check())
assert adapter.app.openapi() == json.loads((root / 'openapi.json').read_bytes())
""",
                    str(rest_output),
                ],
                cwd=root,
                check=True,
            )
        # MCP generation itself must work without the SDK installed in Apizr's env.
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import importlib.util; assert importlib.util.find_spec('mcp') is None",
            ],
            cwd=root,
            check=True,
        )
        runtime_env = root / "mcp-env"
        subprocess.run(
            ["uv", "venv", "--python", args.python, str(runtime_env)], check=True
        )
        runtime_python = (
            runtime_env / ("Scripts" if sys.platform == "win32" else "bin") / "python"
        )
        for target in (source, local_notebook):
            mcp_output = root / (
                "mcp-notebook" if target.suffix == ".ipynb" else "mcp-python"
            )
            subprocess.run(
                [
                    str(cli),
                    "generate",
                    "mcp",
                    str(target),
                    "--module-name",
                    "installed.sample",
                    "--output-dir",
                    str(mcp_output),
                ],
                cwd=root,
                check=True,
            )
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(runtime_python),
                    "-r",
                    str(mcp_output / "requirements.txt"),
                ],
                check=True,
            )
            subprocess.run(
                [
                    str(runtime_python),
                    "-I",
                    "-c",
                    """import asyncio, importlib.util, sys
from mcp import Client, StdioServerParameters
assert importlib.util.find_spec('apizr') is None
assert importlib.util.find_spec('fastapi') is None
async def check():
    async with Client(StdioServerParameters(command=sys.executable, args=[sys.argv[1], '--transport', 'stdio'])) as client:
        assert client.protocol_version == '2026-07-28'
        assert [t.name for t in (await client.list_tools()).tools] == ['total']
        result = await client.call_tool('total', {'values':[1,2]})
        assert not result.is_error and result.structured_content == 3
asyncio.run(check())
""",
                    str(mcp_output / "server.py"),
                ],
                cwd=root,
                check=True,
            )
        # Governed bundles run in environments with no Apizr installation.
        rest_env = root / "governed-rest-env"
        subprocess.run(
            ["uv", "venv", "--python", args.python, str(rest_env)], check=True
        )
        rest_python = (
            rest_env / ("Scripts" if sys.platform == "win32" else "bin") / "python"
        )
        governed_probes = {}
        for target in (source, local_notebook):
            for transport in ("rest", "mcp"):
                output = root / ("governed-" + transport + "-" + target.suffix[1:])
                generated = subprocess.run(
                    [
                        str(cli),
                        "generate",
                        transport,
                        str(target),
                        "--module-name",
                        "installed.sample",
                        "--execution-policy",
                        str(policy),
                        "--output-dir",
                        str(output),
                    ],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
                assert json.loads(generated.stdout)["execution"]["mode"] == "governed"
                target_python = rest_python if transport == "rest" else runtime_python
                subprocess.run(
                    [
                        "uv",
                        "pip",
                        "install",
                        "--python",
                        str(target_python),
                        "-r",
                        str(output / "requirements.txt"),
                    ],
                    check=True,
                )
                if transport == "rest":
                    probe = """import asyncio, importlib.util, json, runpy, sys
assert importlib.util.find_spec('apizr') is None
app = runpy.run_path(sys.argv[1])['app']
assert 'installed.sample' not in sys.modules
async def check():
    messages=[]
    async def receive():
        return {'type':'http.request','body':b'{"values":[1,2]}','more_body':False}
    async def send(message): messages.append(message)
    await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
        'method':'POST','scheme':'http','path':'/capabilities/total','raw_path':b'/capabilities/total',
        'query_string':b'','headers':[(b'content-type',b'application/json')],
        'root_path':'','client':('127.0.0.1',1),'server':('localhost',80)},receive,send)
    assert messages[0]['status']==200,messages
    assert json.loads(b''.join(m.get('body',b'') for m in messages))==3
asyncio.run(check())
assert 'installed.sample' not in sys.modules
"""
                else:
                    probe = """import asyncio, importlib.util, sys
from mcp import Client, StdioServerParameters
assert importlib.util.find_spec('apizr') is None
assert importlib.util.find_spec('fastapi') is None
async def check():
    async with Client(StdioServerParameters(command=sys.executable,args=[sys.argv[1],'--transport','stdio'])) as client:
        assert client.protocol_version=='2026-07-28'
        result=await client.call_tool('total',{'values':[1,2]})
        assert not result.is_error and result.structured_content==3,result
asyncio.run(check())
"""
                governed_probes[transport] = probe
                subprocess.run(
                    [
                        str(target_python),
                        "-I",
                        "-c",
                        probe,
                        str(
                            output / ("app.py" if transport == "rest" else "server.py")
                        ),
                    ],
                    cwd=root,
                    check=True,
                    timeout=30,
                )
        # Repository exposure is exercised from the installed wheel, outside the
        # checkout. Each emitted runtime runs in a requirements-only environment.
        repository = root / "repository-smoke"
        repository.mkdir()
        (repository / "billing.py").write_text(
            "def total(values: list[int]) -> int: return sum(values)\n"
        )
        local_policy = root / "repository-local-policy.json"
        local_policy.write_text("{}")
        oci_policy = root / "repository-oci-policy.json"
        oci_policy.write_text('{"schema_version":"apizr.execution/v2"}')
        image_identity = (
            json.loads(args.runtime_image_config.read_text())
            if args.runtime_image_config
            else {"image": "sha256:" + "0" * 64, "platform": "linux/amd64"}
        )
        if args.runtime_image_config:
            strict_source = root / "deny_probe.py"
            strict_source.write_text(
                "import os\ndef denied() -> bool:\n    try:\n        pid = os.fork()\n    except PermissionError:\n        return True\n    if pid == 0: os._exit(0)\n    os.waitpid(pid, 0)\n    return False\n"
            )
            strict_policy = root / "deny-policy.json"
            strict_policy.write_text(
                '{"schema_version":"apizr.execution/v2","subprocess":{"mode":"deny"}}'
            )
            strict_arguments = root / "deny-arguments.json"
            strict_arguments.write_text("{}")
            result = subprocess.run(
                [
                    str(cli),
                    "execute",
                    str(strict_source),
                    "denied",
                    "--arguments",
                    str(strict_arguments),
                    "--policy",
                    str(strict_policy),
                    "--runtime-image",
                    image_identity["image"],
                    "--runtime-platform",
                    image_identity["platform"],
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert json.loads(result.stdout)["value"] is True
        for profile in ("direct", "local-process", "oci-container", "oci-deny"):
            backend = "oci-container" if profile == "oci-deny" else profile
            oci_policy.write_text(
                json.dumps(
                    {
                        "schema_version": "apizr.execution/v2",
                        "subprocess": {
                            "mode": "deny" if profile == "oci-deny" else "allow"
                        },
                    }
                )
            )
            readiness_config = root / "repository-readiness-policy.json"
            readiness_config.write_text(json.dumps({"execution": {"modes": [backend]}}))
            for transport in ("rest", "mcp"):
                output = root / ("repository-" + profile + "-" + transport)
                flags = [
                    str(repository),
                    "--interface",
                    transport,
                    "--execution-mode",
                    backend,
                    "--select",
                    "python:billing:total",
                    "--readiness-policy",
                    str(readiness_config),
                ]
                planned = subprocess.run(
                    [str(cli), "expose", "plan", *flags, "--plan"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    timeout=20,
                )
                assert (
                    json.loads(planned.stdout)["capabilities"][0]["capability_id"]
                    == "python:billing:total"
                )
                execution_flags = []
                if backend != "direct":
                    execution_flags = [
                        "--execution-policy",
                        str(local_policy if backend == "local-process" else oci_policy),
                    ]
                if backend == "oci-container":
                    execution_flags += [
                        "--runtime-image",
                        image_identity["image"],
                        "--runtime-platform",
                        image_identity["platform"],
                    ]
                subprocess.run(
                    [
                        str(cli),
                        "expose",
                        "build",
                        transport,
                        *flags,
                        *execution_flags,
                        "--output-dir",
                        str(output),
                    ],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                manifest = json.loads(
                    (output / f"apizr-repository-{transport}.json").read_bytes()
                )
                assert manifest["schema_version"] == f"apizr.repository-{transport}/v1"
                if backend != "direct":
                    assert (
                        json.loads((output / "execution/bundle.json").read_bytes())[
                            "backend"
                        ]
                        == backend
                    )
                if backend != "oci-container" or args.runtime_image_config:
                    probe = (
                        governed_probes[transport]
                        .replace("/capabilities/total", "/capabilities/billing.total")
                        .replace("call_tool('total'", "call_tool('billing.total'")
                    )
                    if backend == "direct" and transport == "rest":
                        probe = probe.replace(
                            "app = runpy.run_path(sys.argv[1])['app']",
                            "from pathlib import Path\nsys.path.insert(0, str(Path(sys.argv[1]).parent))\napp = runpy.run_path(sys.argv[1])['app']",
                        )
                    subprocess.run(
                        [
                            str(rest_python if transport == "rest" else runtime_python),
                            "-I",
                            "-c",
                            probe,
                            str(
                                output
                                / ("app.py" if transport == "rest" else "server.py")
                            ),
                        ],
                        cwd=root,
                        check=True,
                        timeout=30,
                    )
        print(
            "Installed repository exposure planning and direct/local/OCI generation passed outside checkout."
        )
        if args.runtime_image_config:
            image_config = json.loads(args.runtime_image_config.read_text())
            container_policy = root / "container-policy.json"
            container_policy.write_text('{"schema_version":"apizr.execution/v2"}')
            for target in (source, local_notebook):
                container_result = subprocess.run(
                    [
                        str(cli),
                        "execute",
                        str(target),
                        "total",
                        "--arguments",
                        str(arguments),
                        "--policy",
                        str(container_policy),
                        "--runtime-image",
                        image_config["image"],
                        "--runtime-platform",
                        image_config["platform"],
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
                assert json.loads(container_result.stdout) == {
                    "schema_version": "apizr.execution-result/v2",
                    "status": "success",
                    "value": 3,
                }, container_result.stdout
                for transport in ("rest", "mcp"):
                    output = root / ("oci-" + transport + "-" + target.suffix[1:])
                    generated = subprocess.run(
                        [
                            str(cli),
                            "generate",
                            transport,
                            str(target),
                            "--execution-policy",
                            str(container_policy),
                            "--runtime-image",
                            image_config["image"],
                            "--runtime-platform",
                            image_config["platform"],
                            "--module-name",
                            "installed.sample",
                            "--output-dir",
                            str(output),
                        ],
                        cwd=root,
                        check=True,
                        capture_output=True,
                    )
                    assert (
                        json.loads(generated.stdout)["execution"]["backend"]
                        == "oci-container"
                    )
                    # Reuse environments already populated only from generated
                    # requirements; neither contains outerspace-apizr.
                    target_python = (
                        rest_python if transport == "rest" else runtime_python
                    )
                    subprocess.run(
                        [
                            str(target_python),
                            "-I",
                            "-c",
                            governed_probes[transport],
                            str(
                                output
                                / ("app.py" if transport == "rest" else "server.py")
                            ),
                        ],
                        cwd=root,
                        check=True,
                        timeout=30,
                    )
            print(
                "Installed-wheel OCI execution and standalone REST/MCP (Python/notebook) passed outside checkout."
            )
        result = subprocess.run(
            [
                str(cli),
                "--notebook",
                str(notebook),
                "--output-dir",
                str(root / "project"),
                "--force",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        manifest = json.loads(result.stdout)
        assert manifest["api_module"] == "pricing_api"
        assert {
            "pricing.py",
            "pricing.json",
            "pricing_api.py",
            "requirements.txt",
            "Dockerfile",
            "start.sh",
        } <= set(manifest["files"])
        for name in manifest["files"]:
            assert (root / "project" / name).is_file()
        # Install a separate distribution and activate its versioned entry point.
        # The CLI and Apizr imports still come exclusively from the candidate wheel.
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                str(Path(__file__).resolve().parents[1] / "examples/pipeline-plugin"),
            ],
            cwd=root,
            check=True,
        )
        config = root / "plugin.yaml"
        config.write_text(
            "plugin_options:\n  delivery-note:\n    project: installed-wheel\n"
        )
        (root / "settings.json").write_text('{"value": 5}')
        for enabled in (False, True):
            output = root / ("plugin-on" if enabled else "plugin-off")
            command = [
                str(cli),
                "--notebook",
                str(local_notebook),
                "--output-dir",
                str(output),
                "--configuration",
                str(config),
                "--include",
                "settings.json",
            ]
            if enabled:
                command += ["--plugin", "delivery-note"]
            subprocess.run(command, cwd=root, check=True, stdout=subprocess.DEVNULL)
            assert (output / "settings.json").read_text() == '{"value": 5}'
            assert (output / "delivery.json").exists() == enabled
        assert json.loads((root / "plugin-on/delivery.json").read_text()) == {
            "api_module": "sample_api",
            "project": "installed-wheel",
        }
        print(
            "Installed external pipeline plugin: explicit activation/options and resource delivery passed."
        )
        print(
            "Wheel namespace, IR/readiness, governed execution, inspection and direct/governed standalone REST/MCP generation/runtime (Python/notebook), resources, license, CLI help and legacy notebook generation passed."
        )


if __name__ == "__main__":
    main()
