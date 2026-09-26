"""Run the exact introductory repository README/docs example using an installed CLI."""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    cli = args.cli.resolve()
    repository = Path(__file__).resolve().parents[1]
    readme = (repository / "README.md").read_text()
    guide = (repository / "docs/getting-started/introduction.md").read_text()
    assert "https://apizr.outerspace.sh/getting-started/quickstart/" in readme
    assert "https://apizr.outerspace.sh/getting-started/introduction/" in readme
    sources = re.findall(r"```python\n(.*?)```", guide, re.S)
    assert len(sources) == 3
    policies = re.findall(r"```json\n(.*?)```", guide, re.S)
    assert len(policies) == 2
    commands = []
    for block in re.findall(r"```sh\n(.*?)```", guide, re.S):
        for line in block.splitlines():
            if line.startswith(
                ("apizr scan", "apizr graph", "apizr readiness", "apizr expose")
            ):
                commands.append(shlex.split(line))
    assert len(commands) == 6
    with tempfile.TemporaryDirectory(prefix="apizr-readme-") as directory:
        root = Path(directory).resolve()
        for name, source in zip(
            ("pricing.py", "inventory.py", "api.py"), sources, strict=True
        ):
            assert (
                source == (repository / "examples/repository-shop" / name).read_text()
            )
            (root / name).write_text(source)
        for name, policy in zip(
            ("readiness-direct.json", "exposure-direct.json"), policies, strict=True
        ):
            assert json.loads(policy) == json.loads(
                (repository / "examples/policies" / name).read_bytes()
            )
            (root / name).write_text(policy)
        for command in commands:
            result = subprocess.run(
                [str(cli), *command[1:]],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # The documented private helper is conditional; this is evidence, not
            # a failed selected capability or permission to widen its eligibility.
            assert result.returncode == (1 if command[1] == "readiness" else 0), (
                result.stderr
            )
            print(f"$ {' '.join(command)}\n{result.stdout}")
        schema = json.loads((root / ".output/rest/openapi.json").read_text())
        assert {
            path for path in schema["paths"] if path.startswith("/capabilities/")
        } == {
            "/capabilities/api.quote",
            "/capabilities/inventory.available",
        }
        tools = json.loads((root / ".output/mcp/mcp-tools.json").read_bytes())
        assert {t["name"] for t in tools["tools"]} == {
            "api.quote",
            "inventory.available",
        }
        assert (root / ".output/mcp/server.py").is_file()

    if args.development:
        development(cli, repository)
    else:
        quickstart(cli, repository)


def quickstart(cli: Path, repository: Path) -> None:
    """Run the published stable shell blocks verbatim, including real client calls."""
    guide = (repository / "docs/getting-started/quickstart.md").read_text()
    blocks = dict(
        re.findall(r"<!-- quickstart:([a-z-]+) -->\s*```sh\n(.*?)```", guide, re.S)
    )
    order = (
        "setup",
        "sources",
        "policies",
        "generate-mcp",
        "install-mcp",
        "client",
        "generate-rest",
        "serve-rest",
        "call-rest",
    )
    assert set(blocks) == set(order)
    assert "outerspace-apizr==0.3.0" in blocks["setup"]
    assert "/v0.3.0/examples/repository-shop/" in blocks["sources"]
    env = dict(
        os.environ, PATH=str(cli.parent) + os.pathsep + os.environ.get("PATH", "")
    )
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="apizr-quickstart-proof-") as directory:
        parent = Path(directory).resolve()
        assert not parent.is_relative_to(repository)
        script = "set -eu\n" + "\n".join(blocks[name] for name in order[:-2])
        result = subprocess.run(
            ["/bin/sh", "-c", script],
            cwd=parent,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        result.check_returncode()
        for expected in (
            "tools: api.quote, inventory.available",
            "quote: 25.0",
            "available: true",
        ):
            assert expected in result.stdout
        root = parent / "apizr-quickstart"
        python = root / ".venv/bin/python"
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import apizr,importlib.metadata; from pathlib import Path; "
                "assert importlib.metadata.version('outerspace-apizr') == '0.3.0'; "
                f"assert not Path(apizr.__file__).resolve().is_relative_to(Path({str(repository)!r}))",
            ],
            cwd=root,
            check=True,
            timeout=10,
        )
        for name in ("api.py", "inventory.py", "pricing.py"):
            assert (root / "shop" / name).read_bytes() == (
                repository / "examples/repository-shop" / name
            ).read_bytes()
        env["PATH"] = str(python.parent) + os.pathsep + env["PATH"]
        # Execute the documented server argv, retaining a bounded lifecycle for CI.
        with (root / "rest.log").open("w+") as log:
            process = subprocess.Popen(
                shlex.split(blocks["serve-rest"]),
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 15
                while True:
                    assert process.poll() is None, "Documented REST server exited"
                    try:
                        with urlopen(
                            "http://127.0.0.1:8000/openapi.json", timeout=1
                        ) as response:
                            schema = json.load(response)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                "Documented REST server not ready"
                            ) from None
                        time.sleep(0.05)
                assert {
                    p for p in schema["paths"] if p.startswith("/capabilities/")
                } == {
                    "/capabilities/api.quote",
                    "/capabilities/inventory.available",
                }
                for line, expected in zip(
                    blocks["call-rest"].strip().splitlines(), (25.0, True), strict=True
                ):
                    call = subprocess.run(
                        shlex.split(line),
                        cwd=root,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=10,
                    )
                    assert json.loads(call.stdout) == expected
                    print(f"$ {line}\n{call.stdout}")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        print(
            "PASS: stable Quickstart outside checkout; two selected MCP tools and REST calls; no graphical client claimed"
        )


def development(cli: Path, repository: Path) -> None:
    """Run the marked development commands from the actual published Markdown."""
    guide = (repository / "docs/development/0.4.md").read_text()
    match = re.search(r"<!-- smoke:development -->\s*```sh\n(.*?)```", guide, re.S)
    assert match
    with tempfile.TemporaryDirectory(prefix="apizr-docs-dev-") as directory:
        root = Path(directory)
        shutil.copytree(repository / "examples/project-config", root / "project-config")
        for line in match[1].strip().splitlines():
            command = shlex.split(line)
            assert command.pop(0) == "core/bin/apizr"
            output = None
            if ">" in command:
                index = command.index(">")
                output = root / command[index + 1]
                command = command[:index]
            result = subprocess.run(
                [str(cli), *command],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            if output:
                json.loads(result.stdout)
                output.write_text(result.stdout)
            print(f"$ {line}\n{result.stdout}")
        schema = json.loads((root / "build/rest/openapi.json").read_text())
        assert "/capabilities/calculator.add" in schema["paths"]
        tools = json.loads((root / "build/mcp/mcp-tools.json").read_text())
        assert [tool["name"] for tool in tools["tools"]] == ["calculator.add"]


def delivery_results(proof: Path) -> None:
    """Test the documented result extraction using the existing real OCI proof."""
    repository = Path(__file__).resolve().parents[1]
    guide = (repository / "docs/development/0.4.md").read_text()
    snippets = re.findall(r"core/bin/python - <<'PY'\n(.*?)\nPY", guide, re.S)
    assert len(snippets) == 2
    builds = json.loads((proof / "results.json").read_text())
    pushes = json.loads((proof / "push-results.json").read_text())
    with tempfile.TemporaryDirectory(prefix="apizr-docs-results-") as directory:
        root = Path(directory)
        for build, push in zip(builds, pushes, strict=True):
            (root / "build-response.json").write_text(json.dumps(build))
            # The existing fixture retains push result objects, after validating
            # the extension envelope. Restore only the envelope fields read here.
            (root / "push-response.json").write_text(
                json.dumps({"status": "ok", "result": push})
            )
            for snippet in snippets:
                subprocess.run(
                    [sys.executable, "-c", snippet], cwd=root, check=True, timeout=10
                )
            assert (
                json.loads((root / "build-result.json").read_text()) == build["result"]
            )
            assert json.loads((root / "push-result.json").read_text()) == push
    (proof / "documentation-results.json").write_text(
        json.dumps({"result_extraction": "passed", "interfaces": len(builds)})
    )


if __name__ == "__main__":
    main()
