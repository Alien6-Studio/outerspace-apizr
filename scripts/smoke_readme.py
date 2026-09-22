"""Run the exact introductory repository README/docs example using an installed CLI."""

import argparse
import json
import re
import shlex
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
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


if __name__ == "__main__":
    main()
