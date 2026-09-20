"""Validate a built wheel and exercise its installed CLI outside the checkout."""

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "apizr/__init__.py" in names
        assert "apizr/capabilities/model.py" in names
        assert "apizr/readiness/model.py" in names
        assert "apizr/generators/rest/runtime.py" in names
        assert "apizr/generators/rest/templates/preamble.txt" in names
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
            ["uv", "pip", "install", "--python", str(python), str(wheel)], check=True
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
        # Both inputs live outside the repository; the installed CLI must be sufficient.
        source = root / "sample.py"
        source.write_text("def total(values: list[int]) -> int: return sum(values)\n")
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
        for target in (source, local_notebook):
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
        print(
            "Wheel namespace, IR/readiness, inspection and REST/MCP generation/runtime (Python/notebook), resources, license, CLI help and legacy notebook generation passed."
        )


if __name__ == "__main__":
    main()
