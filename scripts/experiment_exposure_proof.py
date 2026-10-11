"""Installed Run → ordinary REST/MCP proof, with no checkout imports."""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

import anyio
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def prove(python: Path, fixtures: Path, *, notebook: bool = False) -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    python = python.absolute()
    with tempfile.TemporaryDirectory(prefix="apizr-exposure-installed-") as folder:
        root = Path(folder).resolve()
        project = root / "research"
        shutil.copytree(fixtures / "project", project)
        script = project / "serving.py"
        for name in ("model.json", "debug.json"):
            (project / name).unlink()
            assert not (project / name).exists()
        if notebook:
            source = script.read_text()
            script.unlink()
            script = project / "serving.ipynb"
            script.write_text(
                json.dumps(
                    {
                        "nbformat": 4,
                        "nbformat_minor": 5,
                        "metadata": {},
                        "cells": [
                            {
                                "cell_type": "code",
                                "id": "serving",
                                "metadata": {},
                                "execution_count": None,
                                "outputs": [],
                                "source": source,
                            }
                        ],
                    }
                )
            )

        def command(*arguments):
            completed = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-m",
                    "apizr.cli",
                    "experiment",
                    *map(str, arguments),
                ],
                cwd=root,
                env=env,
                capture_output=True,
                timeout=60,
            )
            assert completed.returncode == 0, completed.stderr.decode()
            return json.loads(completed.stdout)

        probe = subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import sys,apizr.experiments.exposure as m; from pathlib import Path; root=Path(sys.argv[1]); assert not Path(m.__file__).resolve().is_relative_to(root); assert all(not Path(p).resolve().is_relative_to(root) for p in sys.path)",
                str(ROOT),
            ],
            cwd=root,
            env=env,
            capture_output=True,
            timeout=10,
        )
        assert probe.returncode == 0, probe.stderr.decode()
        operator = root / "operator.json"
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
        source = script.read_bytes()
        run = command(
            "run",
            script,
            "--root",
            project,
            "--output",
            "model=model.json",
            "--output",
            "debug=debug.json",
            "--format",
            "json",
        )
        assert run["status"] == "success"
        assert script.read_bytes() == source
        assert (project / "model.json").read_bytes() == b'{"multiplier": 3}'
        assert (project / "debug.json").read_bytes() == b'{"private": true}'
        bindings = {}
        for interface in ("rest", "mcp"):
            result = command(
                "expose",
                run["run_digest"],
                "--root",
                project,
                "--operator-policy",
                operator,
                "--capability",
                "python:serving:predict",
                "--interface",
                interface,
                "--artifact",
                "model",
                "--output-dir",
                root / interface,
                "--format",
                "json",
            )
            bindings[interface] = result["binding"]
            assert bindings[interface]["run_digest"] == run["run_digest"]
            assert bindings[interface]["plan_digest"] == run["plan_digest"]
            assert [o["name"] for o in bindings[interface]["outputs"]] == ["model"]
            assert not (root / interface / "source/debug.json").exists()
            manifest = (
                root / interface / f"apizr-repository-{interface}.json"
            ).read_bytes()
            assert (
                sha256(manifest).hexdigest()
                == result["bundle_manifest_digest"]["value"]
            )
        assert bindings["rest"]["outputs"] == bindings["mcp"]["outputs"]
        assert (
            bindings["rest"]["repository_digest"]
            == bindings["mcp"]["repository_digest"]
        )
        shutil.rmtree(project)
        expected = {"predictions": [[12, True]]}
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        server = "import sys; sys.path.insert(0,sys.argv[1]); from app import app; import uvicorn; assert not any(n=='apizr' or n.startswith('apizr.') for n in sys.modules); uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='error')"
        with (root / "rest.log").open("w+") as log:
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", server, str(root / "rest"), str(port)],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 20
                while True:
                    try:
                        with urlopen(url + "/health", timeout=1) as response:
                            assert json.load(response) == {"status": "ok"}
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            raise AssertionError(log.read()) from None
                        time.sleep(0.05)
                with urlopen(
                    Request(
                        url + "/capabilities/serving.predict",
                        data=b'{"request":{"value":4}}',
                        headers={"Content-Type": "application/json"},
                    ),
                    timeout=10,
                ) as response:
                    assert json.load(response) == expected
                with urlopen(url + "/openapi.json", timeout=10) as response:
                    paths = json.load(response)["paths"]
                    assert [
                        path for path, methods in paths.items() if "post" in methods
                    ] == ["/capabilities/serving.predict"]
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

        async def mcp():
            async with Client(
                StdioServerParameters(
                    command=sys.executable,
                    args=[str(root / "mcp/server.py")],
                    cwd=root,
                    env=env,
                ),
                read_timeout_seconds=10,
            ) as client:
                assert [tool.name for tool in (await client.list_tools()).tools] == [
                    "serving.predict"
                ]
                result = await client.call_tool(
                    "serving.predict", {"request": {"value": 4}}
                )
                assert not result.is_error and result.structured_content == expected

        anyio.run(mcp)
        assert not (root / "model.json").exists()
        assert not (root / "debug.json").exists()
        return {
            "status": "passed",
            "installed_outside_checkout": True,
            "kind": "notebook" if notebook else "python",
            "run_digest": run["run_digest"],
            "plan_digest": run["plan_digest"],
            "binding_schema": "apizr.experiment-exposure/v1",
            "rest": expected,
            "mcp": expected,
            "public_capabilities": ["python:serving:predict"],
            "selected_outputs": ["model"],
            "outputs_created_by_run": True,
            "after_project_and_store_removal": "passed",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--notebook", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prove(args.python, args.fixtures, notebook=args.notebook)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
