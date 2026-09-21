"""Run the exact introductory README/docs example using an installed CLI."""

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
    source = re.findall(r"```python\n(.*?)```", readme, re.S)[0]
    assert source == re.findall(r"```python\n(.*?)```", guide, re.S)[0]
    commands = []
    for block in re.findall(r"```sh\n(.*?)```", readme, re.S):
        for line in block.splitlines():
            if line.startswith(
                (
                    "apizr scan",
                    "apizr graph",
                    "apizr inspect",
                    "apizr readiness",
                    "apizr generate",
                )
            ):
                assert line in guide, line
                commands.append(shlex.split(line))
    assert len(commands) == 6
    with tempfile.TemporaryDirectory(prefix="apizr-readme-") as directory:
        root = Path(directory).resolve()
        (root / "example.py").write_text(source)
        for command in commands:
            result = subprocess.run(
                [str(cli), *command[1:]],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            print(f"$ {' '.join(command)}\n{result.stdout}")
        schema = json.loads((root / ".output/rest/openapi.json").read_text())
        assert "/capabilities/total" in schema["paths"]
        assert (root / ".output/mcp/server.py").is_file()
        assert (root / ".output/mcp/mcp-tools.json").is_file()


if __name__ == "__main__":
    main()
