"""Run the exact introductory repository README/docs example using an installed CLI."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    cli = args.cli.resolve()
    repository = Path(__file__).resolve().parents[1]
    readme = (repository / "README.md").read_text()
    guide = (repository / "docs/getting-started/introduction.md").read_text()
    sources = re.findall(r"```python\n(.*?)```", readme, re.S)
    assert sources == re.findall(r"```python\n(.*?)```", guide, re.S)
    assert len(sources) == 3
    policies = re.findall(r"```json\n(.*?)```", readme, re.S)
    assert policies == re.findall(r"```json\n(.*?)```", guide, re.S)
    assert len(policies) == 2
    commands = []
    for block in re.findall(r"```sh\n(.*?)```", readme, re.S):
        for line in block.splitlines():
            if line.startswith(
                ("apizr scan", "apizr graph", "apizr readiness", "apizr expose")
            ):
                assert line in guide, line
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
