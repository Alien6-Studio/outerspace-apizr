"""Installed-wheel, official-format and source-free REST client qualification."""

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_URL = "https://raw.githubusercontent.com/Kong/insomnia/ab658aa7e419ff155511370dff3d32d53ae5ea53/schemas/insomnia.schema.5.1.json"
SCHEMA_SHA = "65b37ac4118a89aa8b15e381e5bafdc7a8580f3c386b6c65b4db8ba04a86fa17"
SOURCE = '''from typing import Literal
def echo(count: int, enabled: bool, words: list[str], mode: Literal["café", "other"], choice: str | int, suffix: str = "default") -> dict:
    """Return the supplied minimal arguments and the untouched default."""
    return {"count": count, "enabled": enabled, "words": words, "mode": mode, "choice": choice, "suffix": suffix}
def total(values: list[float], extra: float = 1.5) -> float:
    return sum(values) + extra
'''


def run(args, *, cwd, timeout=180, env=None):
    result = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        timeout=timeout,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def write(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def generate(root):
    from apizr.exposure import ExposurePolicy
    from apizr.repository_interfaces.output import write_bundle
    from apizr.repository_readiness import RepositoryReadinessPolicy
    from apizr.workspace.compiler import prepare_exposure, render_bundle
    from apizr.workspace.operator_policy import OperatorPolicy

    source = root / "original-source"
    source.mkdir()
    (source / "sample.py").write_text(SOURCE, encoding="utf-8")
    policy = OperatorPolicy.model_validate_json(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": {"kind": "local", "root": str(source)},
                        "permissions": ["source.analyze"],
                    }
                ],
            }
        )
    )
    prepared = prepare_exposure(
        source,
        operator_policy=policy,
        policy=ExposurePolicy.model_validate(
            {
                "selection": {"include": ["python:sample:echo", "python:sample:total"]},
                "interfaces": ["rest"],
                "execution": {"allowed": ["direct"]},
            }
        ),
        readiness_policy=RepositoryReadinessPolicy.model_validate(
            {"execution": {"modes": ["direct"]}}
        ),
    )
    write_bundle(root / "rest", render_bundle(prepared, interface="rest"))


def export(root, base_url):
    from apizr.client_collections import (
        canonical_bytes,
        export_client_collection,
        plan_client_collection,
    )

    collection = plan_client_collection(root / "rest", base_url=base_url)
    (root / "collection-ir.json").write_bytes(canonical_bytes(collection))
    results = {}
    for format in ("postman", "bruno", "insomnia"):
        result = export_client_collection(
            root / "rest", format=format, output_dir=root / format, base_url=base_url
        )
        results[format] = result.model_dump(mode="json")
    write(root / "export-results.json", results)


def qualify(args):
    import jsonschema
    import yaml

    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    wheel_dir = root / "wheels"
    run(["uv", "build", "--wheel", ROOT, "--out-dir", wheel_dir], cwd=root)
    wheel = next(wheel_dir.glob("*.whl"))
    for environment in ("minimal", "clients", "service"):
        run(["uv", "venv", "--python", sys.executable, root / environment], cwd=root)
    minimal = root / "minimal/bin/python"
    python = root / "clients/bin/python"
    run(["uv", "pip", "install", "--python", minimal, wheel], cwd=root)
    run(
        [
            minimal,
            "-I",
            "-c",
            "from importlib.util import find_spec; from importlib.metadata import requires; import apizr.client_collections; assert find_spec('yaml') is None; assert [r for r in requires('outerspace-apizr') if 'extra ==' not in r] == ['pydantic<3,>=2.12']; print('minimal core: Pydantic only, no YAML')",
        ],
        cwd=root,
    )
    run(
        ["uv", "pip", "install", "--python", python, str(wheel) + "[clients]"], cwd=root
    )
    proof = Path(__file__).resolve()
    run([python, "-I", proof, "--generate", root], cwd=root)
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            root / "service/bin/python",
            "-r",
            root / "rest/requirements.txt",
        ],
        cwd=root,
    )
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    run([python, "-I", proof, "--export", root, "--base-url", url], cwd=root)
    shutil.rmtree(root / "original-source")
    assert not (root / "original-source").exists()
    collection = json.loads((root / "collection-ir.json").read_bytes())
    expected = {
        "sample.echo": {
            "count": 0,
            "enabled": False,
            "words": [],
            "mode": "café",
            "choice": "",
            "suffix": "default",
        },
        "sample.total": 1.5,
    }
    service_log = (root / "service.log").open("w")
    process = subprocess.Popen(
        [
            str(root / "service/bin/python"),
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root / "rest",
        stdout=service_log,
        stderr=subprocess.STDOUT,
    )
    validations = {}
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                with urllib.request.urlopen(url + "/health", timeout=1) as response:
                    assert response.status == 200
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("REST fixture did not start") from None
                time.sleep(0.1)
        results = []
        for request in collection["requests"]:
            with urllib.request.urlopen(
                urllib.request.Request(
                    url + request["route"],
                    data=json.dumps(request["example"]).encode(),
                    headers={"Content-Type": "application/json"},
                    method=request["method"],
                ),
                timeout=10,
            ) as response:
                data = json.load(response)
                assert response.status == 200 and data == expected[request["name"]], (
                    data
                )
                results.append(
                    {
                        "capability_id": request["capability_id"],
                        "status": response.status,
                        "result": data,
                    }
                )
        postman = args.postman.resolve()
        assert run([postman, "--version"], cwd=root).strip() == "1.67.0"
        lint = json.loads(
            run(
                [postman, "collection", "lint", root / "postman", "--reporter", "json"],
                cwd=root,
            )
        )
        assert lint["errorCount"] == 0 and lint["warningCount"] == 0
        postman_log = run(
            [
                postman,
                "collection",
                "run",
                root / "postman",
                "--reporters",
                "cli",
                "--verbose",
            ],
            cwd=root,
        )
        (root / "postman-run.log").write_text(postman_log)
        assert postman_log.count("200 OK") == len(results), postman_log
        responses = re.findall(r"  - v [^\n]+\n((?:  \|[^\n]*\n)+)", postman_log)
        assert len(responses) == len(results)
        for response, request in zip(responses, collection["requests"], strict=True):
            assert (
                json.loads(
                    "".join(line.removeprefix("  | ") for line in response.splitlines())
                )
                == expected[request["name"]]
            )
        assert re.findall(r"  POST (\S+)", postman_log) == [
            url + r["route"] for r in collection["requests"]
        ]
        validations["postman"] = {
            "format": "3.0.0",
            "cli": "1.67.0",
            "lint": lint,
            "requests": len(results),
            "reporter": "cli (v3 JSON reporter unsupported)",
        }
        tools = args.tools.resolve()
        bruno = tools / "node_modules/.bin/bru"
        assert run([bruno, "--version"], cwd=root).strip() == "4.2.0"
        schema = json.loads(
            (
                tools
                / "node_modules/@opencollection/schema/src/opencollection.schema.json"
            ).read_bytes()
        )
        bruno_collection = yaml.safe_load(
            (root / "bruno/opencollection.yml").read_bytes()
        )
        bruno_collection["items"] = sorted(
            [
                yaml.safe_load(p.read_bytes())
                for p in (root / "bruno").glob("request-*.yml")
            ],
            key=lambda r: r["info"]["seq"],
        )
        jsonschema.validate(bruno_collection, schema)
        (root / "bruno-run.log").write_text(
            run(
                [bruno, "run", "--reporter-json", root / "bruno-results.json"],
                cwd=root / "bruno",
            )
        )
        bruno_result = json.loads((root / "bruno-results.json").read_text())
        executions = bruno_result[0]["results"]
        assert len(executions) == len(results)
        for execution, request in zip(executions, collection["requests"], strict=True):
            assert execution["response"]["status"] == 200
            assert execution["response"]["data"] == expected[request["name"]]
            assert execution["request"]["method"] == request["method"]
            assert execution["request"]["url"] == url + request["route"]
            assert json.loads(execution["request"]["data"]) == request["example"]
        validations["bruno"] = {
            "format": "1.0.0",
            "cli": "4.2.0",
            "schema_package": "0.14.0",
            "requests": len(executions),
        }
        raw = urllib.request.urlopen(SCHEMA_URL, timeout=30).read()
        assert hashlib.sha256(raw).hexdigest() == SCHEMA_SHA
        insomnia = yaml.safe_load((root / "insomnia/collection.yaml").read_bytes())
        jsonschema.validate(insomnia, json.loads(raw))
        inso = args.inso.resolve()
        assert run([inso, "--version"], cwd=root).strip() == "13.3.0"
        (root / "insomnia-run.log").write_text(
            run(
                [
                    inso,
                    "--ci",
                    "--workingDir",
                    root / "insomnia/collection.yaml",
                    "run",
                    "collection",
                    insomnia["meta"]["id"],
                    "--bail",
                    "--output",
                    root / "insomnia-results.json",
                    "--includeFullData",
                    "plaintext",
                    "--acceptRisk",
                ],
                cwd=root,
            )
        )
        executions = json.loads((root / "insomnia-results.json").read_bytes())[
            "executions"
        ]
        assert len(executions) == len(results)
        for execution, request in zip(executions, collection["requests"], strict=True):
            assert execution["response"]["code"] == 200
            assert (
                json.loads(execution["response"]["data"]) == expected[request["name"]]
            )
            assert execution["request"]["method"] == request["method"]
            assert execution["request"]["url"] == "{{ _.base_url }}" + request["route"]
            assert (
                json.loads(execution["request"]["body"]["text"]) == request["example"]
            )
        validations["insomnia"] = {
            "format": "5.0",
            "schema": "5.1",
            "schema_sha256": SCHEMA_SHA,
            "cli": "13.3.0",
            "requests": len(executions),
        }
        write(root / "request-results.json", results)
        write(
            root / "format-validation.json",
            {
                "source_sha": run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip(),
                "no_source": True,
                "outside_checkout": True,
                "wheel_bytes": wheel.stat().st_size,
                "formats": validations,
            },
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        service_log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", type=Path)
    parser.add_argument("--export", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tools", type=Path)
    parser.add_argument("--postman", type=Path)
    parser.add_argument("--inso", type=Path)
    args = parser.parse_args()
    if args.generate:
        generate(args.generate)
    elif args.export:
        export(args.export, args.base_url)
    else:
        qualify(args)


if __name__ == "__main__":
    main()
