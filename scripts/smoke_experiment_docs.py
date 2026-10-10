"""Execute the marked README, Start Here, Quickstart and experiment guide examples."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = (
    "README.md",
    "docs/getting-started/introduction.md",
    "docs/getting-started/quickstart.md",
    "docs/getting-started/user-guide/experiment-inspection.md",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cli = args.cli.resolve()
    env = {**os.environ, "PATH": str(cli.parent) + os.pathsep + os.environ["PATH"]}
    env.pop("PYTHONPATH", None)
    results = {}
    with tempfile.TemporaryDirectory(prefix="apizr-experiment-docs-") as directory:
        for index, page in enumerate(PAGES):
            root = Path(directory) / str(index)
            shutil.copytree(ROOT / "tests/fixtures/experiments/inspection", root)
            blocks = re.findall(
                r"<!-- experiment-inspection:[a-z-]+ -->\s*```sh\n(.*?)```",
                (ROOT / page).read_text(),
                re.S,
            )
            assert blocks, page
            for block in blocks:
                result = subprocess.run(
                    ["/bin/sh", "-eu", "-c", block],
                    cwd=root,
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                assert not result.stderr, (page, result.stderr)
                assert all(
                    (heading + " — ").encode() in result.stdout
                    for heading in (
                        "Code",
                        "Data",
                        "Parameters",
                        "Randomness",
                        "Environment",
                        "Metrics",
                        "Outputs",
                        "Serving",
                    )
                ), page
            results[page] = {
                "status": "passed",
                "blocks": len(blocks),
                "example_sha256": sha256("\n".join(blocks).encode()).hexdigest(),
            }
        for index, page in enumerate(
            (
                "README.md",
                "docs/getting-started/quickstart.md",
                "docs/getting-started/user-guide/experiment-runs.md",
            )
        ):
            root = Path(directory) / f"runs-{index}"
            root.mkdir()
            blocks = re.findall(
                r"<!-- experiment-run:[a-z-]+ -->\s*```sh\n(.*?)```",
                (ROOT / page).read_text(),
                re.S,
            )
            assert blocks, page
            for block in blocks:
                result = subprocess.run(
                    ["/bin/sh", "-eu", "-c", block],
                    cwd=root,
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                assert b"trusted user code" in result.stderr
                assert b"not a security sandbox" in result.stderr
                assert all(
                    text in result.stdout
                    for text in (
                        b"SUCCESS",
                        b"Run: ",
                        b"Plan: ",
                        b"mean=4.0 (runtime)",
                        b"model.json:",
                        b"runtime application not directly observed",
                    )
                ), page
                assert (
                    len(list((root / ".apizr/experiments/v1/runs").glob("*.json"))) == 1
                )
            results[page + "#run"] = {
                "status": "passed",
                "blocks": len(blocks),
                "example_sha256": sha256("\n".join(blocks).encode()).hexdigest(),
            }
    args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
