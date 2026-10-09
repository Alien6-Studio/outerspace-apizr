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
import tomllib
from pathlib import Path
from urllib.request import urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--expected-version")
    parser.add_argument(
        "--repository-refinement",
        action="store_true",
        help="Expect the candidate's proven local imports to refine repository readiness",
    )
    args = parser.parse_args()
    if args.repository_refinement and not args.development:
        parser.error("--repository-refinement requires --development")
    cli = args.cli.resolve()
    repository = Path(__file__).resolve().parents[1]
    readme = (repository / "README.md").read_text()
    directory = (
        "docs/getting-started"
        if args.development
        else "tests/fixtures/documentation-0.3"
    )
    guide = (repository / directory / "introduction.md").read_text()
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
        if args.development:
            authority = re.search(
                r"<!-- journey:authorization -->\s*```sh\n(.*?)```", guide, re.S
            )
            assert authority
            subprocess.run(
                ["/bin/sh", "-c", "set -eu\n" + authority[1]],
                cwd=root,
                check=True,
                timeout=10,
            )
        for command in commands:
            result = subprocess.run(
                [str(cli), *command[1:]],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Scan retains source-local uncertainty in every version. Only the
            # candidate's repository stage can refine this proven local import.
            expected_exit = (
                1 if command[1] == "readiness" and not args.repository_refinement else 0
            )
            assert result.returncode == expected_exit, (
                command,
                result.returncode,
                result.stdout,
                result.stderr,
            )
            if command[1] == "scan":
                assert "Ready: 3\nConditional: 1\n" in result.stdout
                assert "  _price: CONDITIONAL" in result.stdout
            elif command[1] == "readiness":
                state = "READY" if args.repository_refinement else "CONDITIONAL"
                assert f"python:api:_price: {state}" in result.stdout
                assert (
                    "  local: conditional; interface eligible: false" in result.stdout
                )
                assert "APIZR-READY-015" in result.stdout
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
        migration(cli, repository)
        if args.repository_refinement:
            selected_scope(cli, repository)
            from typed_dict_proof import proof

            proof(cli, Path(sys.executable))
        quickstart(
            cli, repository, candidate=True, expected_version=args.expected_version
        )
    quickstart(cli, repository)


def selected_scope(cli: Path, repository: Path) -> None:
    """Run the documented unfinished-repository example with the candidate."""
    guide = (repository / "docs/getting-started/user-guide/exposure.md").read_text()
    block = re.search(r"<!-- smoke:selected-scope -->\s*```sh\n(.*?)```", guide, re.S)
    assert block
    with tempfile.TemporaryDirectory(prefix="apizr-selected-scope-") as directory:
        root = Path(directory).resolve()
        assert not root.is_relative_to(repository)
        project = root / "project"
        shutil.copytree(repository / "examples/research-serving", project)
        (root / "direct-readiness.json").write_text(
            '{"execution":{"modes":["direct"]}}\n'
        )
        (root / "operator.json").write_text(
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
        environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        environment["PATH"] = str(cli.parent) + os.pathsep + environment.get("PATH", "")
        subprocess.run(
            ["/bin/sh", "-c", "set -eu\n" + block[1]],
            cwd=root,
            env=environment,
            check=True,
            timeout=60,
        )
        plan = json.loads((root / "exposure-plan.json").read_bytes())
        assert [c["capability_id"] for c in plan["capabilities"]] == [
            "python:serving:predict"
        ]
        for interface in ("rest", "mcp"):
            bundle = root / (".output/predict-" + interface)
            graph = json.loads((bundle / "capability-graph.json").read_bytes())
            assert not graph["complete"]
            assert any(d["path"] == "old_notebook.py" for d in graph["diagnostics"])
            assert (bundle / "source/experiments.py").read_bytes() == (
                project / "experiments.py"
            ).read_bytes()
            if interface == "rest":
                paths = json.loads((bundle / "openapi.json").read_bytes())["paths"]
                assert {p for p in paths if p.startswith("/capabilities/")} == {
                    "/capabilities/serving.predict"
                }
            else:
                tools = json.loads((bundle / "mcp-tools.json").read_bytes())["tools"]
                assert [tool["name"] for tool in tools] == ["serving.predict"]
        print("PASS documented serving selection; full ambiguous audit retained")


def quickstart(
    cli: Path,
    repository: Path,
    *,
    candidate: bool = False,
    expected_version: str | None = None,
) -> None:
    """Run the selected Quickstart blocks verbatim, including real client calls."""
    directory = (
        "docs/getting-started" if candidate else "tests/fixtures/documentation-0.3"
    )
    guide = (repository / directory / "quickstart.md").read_text()
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
    if candidate:
        assert "--operator-policy operator.json" in blocks["generate-mcp"]
        assert "--operator-policy operator.json" in blocks["generate-rest"]
    else:
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
            'quote: {"result": 25.0}' if candidate else "quote: 25.0",
            'available: {"result": true}' if candidate else "available: true",
        ):
            assert expected in result.stdout
        root = parent / "apizr-quickstart"
        python = cli.parent / "python" if candidate else root / ".venv/bin/python"
        expected_version = (
            expected_version
            or tomllib.loads((repository / "pyproject.toml").read_text())["project"][
                "version"
            ]
            if candidate
            else "0.3.0"
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import apizr,importlib.metadata; from pathlib import Path; "
                f"assert importlib.metadata.version('outerspace-apizr') == {expected_version!r}; "
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
            f"PASS: {'current 0.4' if candidate else 'historical 0.3'} Quickstart outside checkout; two selected MCP tools and REST calls; no graphical client claimed"
        )


def development(cli: Path, repository: Path) -> None:
    """Run the marked development commands from the actual published Markdown."""
    guide = (repository / "docs/development/0.4.md").read_text()
    match = re.search(r"<!-- smoke:development -->\s*```sh\n(.*?)```", guide, re.S)
    assert match
    with tempfile.TemporaryDirectory(prefix="apizr-docs-dev-") as directory:
        root = Path(directory).resolve()
        shutil.copytree(repository / "examples/project-config", root / "project-config")
        script = (
            match[1]
            .replace("core/bin/apizr", shlex.quote(str(cli)))
            .replace("core/bin/python", shlex.quote(str(cli.parent / "python")))
        )
        result = subprocess.run(
            ["/bin/sh", "-c", "set -eu\n" + script],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        print(result.stdout)
        for name in ("readiness.json", "plan.json"):
            json.loads((root / name).read_text())
        schema = json.loads((root / "build/rest/openapi.json").read_text())
        assert "/capabilities/calculator.add" in schema["paths"]
        tools = json.loads((root / "build/mcp/mcp-tools.json").read_text())
        assert [tool["name"] for tool in tools["tools"]] == ["calculator.add"]


def migration(cli: Path, repository: Path) -> None:
    """Execute the current authorization example with an installed minimal core outside checkout."""
    guide = (repository / "docs/reference/operator-policy.md").read_text()
    blocks = dict(
        re.findall(r"<!-- migration:([a-z]+) -->\s*```sh\n(.*?)```", guide, re.S)
    )
    assert set(blocks) == {"prepare", "refuse", "generate", "python"}
    env = dict(
        os.environ, PATH=str(cli.parent) + os.pathsep + os.environ.get("PATH", "")
    )
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="apizr-migration-proof-") as directory:
        parent = Path(directory).resolve()
        assert not parent.is_relative_to(repository)
        for name in ("prepare", "refuse", "generate", "python"):
            result = subprocess.run(
                ["/bin/sh", "-c", "set -eu\n" + blocks[name]],
                cwd=parent if name == "prepare" else parent / "permissions-demo",
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if name == "refuse":
                assert result.returncode == 2, result.stderr
                assert not result.stdout
                assert json.loads(result.stderr)["code"] == "operator_policy_required"
                continue
            result.check_returncode()
            print(result.stdout)
            if name == "python":
                assert (
                    "CLI/Python parity: plan, REST bundle and MCP bundle"
                    in result.stdout
                )
        root = parent / "permissions-demo/build"
        schema = json.loads((root / "rest/openapi.json").read_text())
        assert {p for p in schema["paths"] if p.startswith("/capabilities/")} == {
            "/capabilities/api.quote",
            "/capabilities/inventory.available",
        }
        tools = json.loads((root / "mcp/mcp-tools.json").read_text())
        assert {tool["name"] for tool in tools["tools"]} == {
            "api.quote",
            "inventory.available",
        }
        print(
            "PASS: installed migration refusal, explicit grants and CLI/Python parity"
        )


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
