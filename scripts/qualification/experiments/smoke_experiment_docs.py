"""Execute the marked README, Start Here, Quickstart and experiment guide examples."""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PAGES = (
    "README.md",
    "tests/fixtures/qualified-guides/getting-started/introduction.md",
    "tests/fixtures/qualified-guides/getting-started/quickstart.md",
    "tests/fixtures/qualified-guides/getting-started/user-guide/experiment-inspection.md",
)


def tracking_examples(cli: Path, root: Path, env: dict[str, str]) -> dict:
    """Run the public SDK guide verbatim with the installed candidate interpreter."""
    page = ROOT / "tests/fixtures/qualified-guides/getting-started/tracking.md"
    blocks = dict(
        re.findall(
            r"<!-- tracking-journey:([a-z-]+) -->\s*```sh\n(.*?)\n```",
            page.read_text(),
            re.S,
        )
    )
    assert set(blocks) == {"session", "decorator", "history", "providers", "telemetry"}
    root.mkdir()
    outputs = {}
    for name, block in blocks.items():
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", block],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (name, result.stdout, result.stderr)
        outputs[name] = result.stdout

    def command(*arguments):
        return json.loads(
            subprocess.run(
                [str(cli), "experiment", *arguments, "--format", "json"],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            ).stdout
        )

    history = command("list")
    assert history["total"] == 3
    records = [command("show", run["run_digest"]) for run in history["runs"]]
    sessions = [r for r in records if r["run"]["capture"]["mode"] == "sdk_session"]
    calls = [r for r in records if r["run"]["capture"]["mode"] == "decorated_call"]
    assert len(sessions) == 1 and len(calls) == 2
    assert math.isclose(sessions[0]["run"]["metrics"][0]["value"], 0.8)
    calls.sort(key=lambda r: r["run"]["call_parameters"][0]["value"])
    assert [r["run"]["call_parameters"][0]["value"] for r in calls] == [0.75, 0.85]
    assert [r["run"]["metrics"][0]["value"] for r in calls] == [2 / 3, 1 / 3]
    difference = command("diff", calls[0]["run_digest"], calls[1]["run_digest"])
    assert difference["schema_version"] == "apizr.experiment-diff/v2"
    assert difference["metrics"][0]["state"] == "changed"
    providers = json.loads((root / "providers.json").read_text())
    assert providers["active"] == [{"name": "apizr.builtin", "version": "1"}]
    inspection = json.loads((root / "inspection.json").read_text())
    assert inspection["providers"]["providers"][0]["diagnostic"] == "provider_disabled"
    assert all(
        owner["state"] == "unknown" for owner in inspection["providers"]["owners"]
    )
    preview = json.loads(outputs["telemetry"])
    assert not preview["collection_enabled"] and not preview["transmission_available"]
    assert json.loads(preview["payload"])["events"] == []
    return {
        "status": "passed",
        "blocks": len(blocks),
        "records": 3,
        "sdk_comparison": "passed",
        "disabled_provider": "unknown",
        "telemetry": "disabled without transmission",
        "page_sha256": sha256(page.read_bytes()).hexdigest(),
    }


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
                "tests/fixtures/qualified-guides/getting-started/quickstart.md",
                "tests/fixtures/qualified-guides/getting-started/user-guide/experiment-runs.md",
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
        for index, page in enumerate(
            (
                "README.md",
                "tests/fixtures/qualified-guides/getting-started/quickstart.md",
                "tests/fixtures/qualified-guides/getting-started/user-guide/experiment-comparison.md",
            )
        ):
            root = Path(directory) / f"diff-{index}"
            root.mkdir()
            blocks = re.findall(
                r"<!-- experiment-diff:[a-z-]+ -->\s*```sh\n(.*?)```",
                (ROOT / page).read_text(),
                re.S,
            )
            assert len(blocks) == 1, page
            result = subprocess.run(
                ["/bin/sh", "-eu", "-c", blocks[0]],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                timeout=60,
            )
            assert b"trusted user code" in result.stderr
            assert all(
                text in result.stdout
                for text in (
                    b"Material evidence differences",
                    b"Observed result differences",
                    b"delta B - A: +0.01",
                    b"Apizr does not establish",
                )
            ), page
            value = json.loads((root / "comparison.json").read_bytes())
            assert value["schema_version"] == "apizr.experiment-diff/v1"
            assert value["metrics"][0]["state"] == "changed"
            assert (
                next(p for p in value["parameters"] if p["name"] == "max_depth")[
                    "planned_state"
                ]
                == "changed"
            )
            assert not (root / "compare_train.py").exists()
            assert len(list((root / ".apizr/experiments/v1/runs").glob("*.json"))) == 2
            results[page + "#diff"] = {
                "status": "passed",
                "blocks": len(blocks),
                "example_sha256": sha256(blocks[0].encode()).hexdigest(),
            }
        page = "tests/fixtures/qualified-guides/getting-started/user-guide/experiment-exposure.md"
        root = Path(directory) / "exposure"
        root.mkdir()
        blocks = re.findall(
            r"<!-- experiment-exposure:[a-z-]+ -->\s*```sh\n(.*?)```",
            (ROOT / page).read_text(),
            re.S,
        )
        assert len(blocks) == 1
        result = subprocess.run(
            ["/bin/sh", "-eu", "-c", blocks[0]],
            cwd=root,
            env=env,
            check=True,
            capture_output=True,
            timeout=60,
        )
        assert b"trusted user code" in result.stderr
        for interface in ("rest", "mcp"):
            value = json.loads((root / f"{interface}-binding.json").read_bytes())
            assert value["binding"]["schema_version"] == "apizr.experiment-exposure/v1"
            assert [item["name"] for item in value["binding"]["outputs"]] == ["model"]
            assert (root / "dist" / interface / "source/model.json").is_file()
            assert not (root / "dist" / interface / "source/debug.json").exists()
        results[page] = {
            "status": "passed",
            "blocks": len(blocks),
            "example_sha256": sha256(blocks[0].encode()).hexdigest(),
        }
        results["tests/fixtures/qualified-guides/getting-started/tracking.md"] = (
            tracking_examples(cli, Path(directory) / "tracking", env)
        )
    args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
