"""Execute the new scenario Markdown against published packages outside checkout."""

import argparse
import hashlib
import json
import os
import re
import shlex
import socket
import subprocess
import time
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-wheelhouse", type=Path)
    args = parser.parse_args()
    python = args.python.absolute()
    output = args.output.resolve()
    assert not output.exists() and not output.is_relative_to(ROOT)
    output.mkdir(parents=True)
    environment = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    environment["PATH"] = str(python.parent) + os.pathsep + environment["PATH"]
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    if args.runtime_wheelhouse:
        environment["PIP_NO_INDEX"] = "1"
        environment["PIP_FIND_LINKS"] = str(args.runtime_wheelhouse.resolve())
    provenance = subprocess.check_output(
        [
            str(python),
            "-I",
            "-c",
            "import apizr,json,sys,platform; from importlib.metadata import version; print(json.dumps({'version':version('outerspace-apizr'),'path':apizr.__file__,'python':sys.version.split()[0],'platform':platform.platform()}))",
        ],
        cwd=output,
        text=True,
        env=environment,
    )
    runtime = json.loads(provenance)
    assert runtime["version"] == "0.4.5"
    assert not Path(runtime["path"]).resolve().is_relative_to(ROOT)
    results = {"runtime": runtime, "scenarios": {}}

    def run(block, cwd, name):
        completed = subprocess.run(
            ["/bin/sh", "-eu", "-c", block],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=300,
        )
        (output / (name + ".log")).write_text(completed.stdout + completed.stderr)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        return completed.stdout

    for archive, page, prefix in (
        ("business-quote", "business-quote", "quote"),
        ("logistics-tool", "logistics-tool", "route"),
        ("research-serving", "research-serving", "research"),
    ):
        parent = output / prefix
        parent.mkdir()
        data = (args.site / "downloads" / (archive + ".zip")).read_bytes()
        with zipfile.ZipFile(args.site / "downloads" / (archive + ".zip")) as zipped:
            zipped.extractall(parent)
        project = parent / archive
        text = (ROOT / "docs/examples" / (page + ".md")).read_text()
        blocks = dict(
            re.findall(r"<!-- scenario:([a-z-]+) -->\s*```sh\n(.*?)```", text, re.S)
        )
        run(blocks[prefix + "-build"], project, prefix + "-build")
        if prefix == "route":
            response = run(blocks["route-call"], project, "route-call")
            assert "estimated_minutes" in response and "unknown_stop" in response
        else:
            if prefix == "research":
                refusal = run(blocks["research-refusal"], project, "research-refusal")
                assert "features" in refusal and "predict" in refusal
                assert json.loads((project / "plan.json").read_text()) == json.loads(
                    (project / "corrected-plan.json").read_text()
                )
            run(blocks[prefix + "-install"], project, prefix + "-install")
            bundle = parent / ("bundles" if prefix == "quote" else "research-bundles")
            schema = json.loads((bundle / "rest/openapi.json").read_text())
            endpoint = "/capabilities/" + (
                "api.quote" if prefix == "quote" else "serving.predict"
            )
            assert {p for p in schema["paths"] if p.startswith("/capabilities/")} == {
                endpoint
            }
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", 8000))
            with (output / (prefix + "-server.log")).open("w") as log:
                server = subprocess.Popen(
                    shlex.split(blocks[prefix + "-serve"]),
                    cwd=project,
                    env=environment,
                    stdout=log,
                    stderr=log,
                )
                try:
                    deadline = time.monotonic() + 30
                    while True:
                        try:
                            with urlopen(
                                "http://127.0.0.1:8000/health", timeout=1
                            ) as response:
                                assert json.load(response) == {"status": "ok"}
                            break
                        except OSError:
                            assert server.poll() is None
                            if time.monotonic() > deadline:
                                raise
                            time.sleep(0.05)
                    response = run(blocks[prefix + "-http"], project, prefix + "-http")
                    actual = json.loads(response)
                    assert (
                        actual["total_cents"] == 9180
                        if prefix == "quote"
                        else actual == 0.4
                    )
                    run(blocks[prefix + "-mcp"], project, prefix + "-mcp")
                    if prefix == "quote":

                        def post(value, endpoint=endpoint):
                            with urlopen(
                                Request(
                                    "http://127.0.0.1:8000" + endpoint,
                                    data=json.dumps(value).encode(),
                                    headers={"Content-Type": "application/json"},
                                ),
                                timeout=10,
                            ) as response:
                                return json.load(response)

                        assert post(
                            {
                                "order": {
                                    "lines": [{"sku": "DESK-LAMP", "quantity": 13}],
                                    "coupon": "none",
                                }
                            }
                        ) == {"ok": False, "reason": "insufficient_stock"}
                        try:
                            post(
                                {
                                    "order": {
                                        "lines": [],
                                        "coupon": "none",
                                        "extra": True,
                                    }
                                }
                            )
                        except HTTPError as error:
                            assert error.code == 422
                        else:
                            raise AssertionError(
                                "Closed input must reject an extra field"
                            )
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=10)
            if prefix == "quote":
                compiler_page = (ROOT / "docs/developer-guide/compiler.md").read_text()
                compiler_match = re.search(
                    r"<!-- compiler:prepare -->\s*```sh\n(.*?)```", compiler_page, re.S
                )
                assert compiler_match is not None, (
                    "Missing documented compiler commands"
                )
                compiler_block = compiler_match.group(1)
                compiler = run(compiler_block, project, "compiler")
                assert "Refused unsupported stream" in compiler
                with (output / "compiler-server.log").open("w") as log:
                    server = subprocess.Popen(
                        shlex.split(
                            blocks["quote-serve"].replace(
                                "../bundles", "../python-bundles"
                            )
                        ),
                        cwd=project,
                        env=environment,
                        stdout=log,
                        stderr=log,
                    )
                    try:
                        deadline = time.monotonic() + 30
                        while True:
                            try:
                                with urlopen(
                                    "http://127.0.0.1:8000/health", timeout=1
                                ) as health:
                                    assert json.load(health) == {"status": "ok"}
                                break
                            except OSError:
                                assert server.poll() is None
                                if time.monotonic() > deadline:
                                    raise
                                time.sleep(0.05)
                        run(blocks["quote-http"], project, "compiler-http")
                        run(
                            blocks["quote-mcp"].replace(
                                "../bundles", "../python-bundles"
                            ),
                            project,
                            "compiler-mcp",
                        )
                    finally:
                        server.terminate()
                        try:
                            server.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            server.kill()
                            server.wait(timeout=10)
        results["scenarios"][prefix] = {
            "status": "passed",
            "archive_sha256": hashlib.sha256(data).hexdigest(),
            "command_sha256": hashlib.sha256(
                json.dumps(blocks, sort_keys=True).encode()
            ).hexdigest(),
            "rest_mcp": prefix != "route",
            "mcp": True,
        }
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
