"""Compare serial and parallel full-suite runs on one source and interpreter."""

import argparse
import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PARALLEL = [
    "-n",
    "auto",
    "--maxprocesses=2",
    "--dist=loadfile",
    "--max-worker-restart=0",
]


def cases(path: Path) -> Counter:
    """Retain each identity, outcome and multiplicity, including skipped cases."""
    root = ET.parse(path).getroot()
    result = Counter()
    for case in root.iter("testcase"):
        outcomes = [
            tag for tag in ("failure", "error", "skipped") if case.find(tag) is not None
        ]
        if len(outcomes) > 1 or any(tag in outcomes for tag in ("failure", "error")):
            raise ValueError("Unsuccessful or ambiguous JUnit outcome")
        result[
            (
                case.attrib["classname"],
                case.attrib["name"],
                outcomes[0] if outcomes else "passed",
            )
        ] += 1
    if not result or not any(key[2] == "passed" for key in result):
        raise ValueError("Empty or entirely skipped JUnit report")
    reported = sum(int(s.attrib["tests"]) for s in root.iter("testsuite"))
    if reported != result.total():
        raise ValueError("Incomplete JUnit report")
    return result


def compare(serial: Path, parallel: Path) -> dict:
    before, after = cases(serial), cases(parallel)
    if before != after:
        raise ValueError(
            "Serial/parallel JUnit identities, outcomes or multiplicities differ"
        )
    identities = json.dumps(sorted(before.items()), ensure_ascii=False).encode()
    return {
        "cases": before.total(),
        "outcomes": {
            status: sum(n for (_, _, outcome), n in before.items() if outcome == status)
            for status in sorted({key[2] for key in before})
        },
        "identities_sha256": hashlib.sha256(identities).hexdigest(),
    }


def coverage_gates() -> list[list[str]]:
    """Use the actual compatibility gates, rather than a second set of floors."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    commands = []
    for step in workflow["jobs"]["compatibility"]["steps"]:
        command = shlex.split(step.get("run", ""))
        if command[:5] == ["uv", "run", "--locked", "coverage", "report"]:
            commands.append([sys.executable, "-m", *command[3:]])
        elif command[:5] == [
            "uv",
            "run",
            "--locked",
            "python",
            "scripts/check_scope_coverage.py",
        ]:
            commands.append([sys.executable, *command[4:]])
    if len(commands) < 23:
        raise ValueError("Missing compatibility coverage gates")
    return commands


def measure(output: Path, flags: list[str], gates: list[list[str]]) -> dict:
    output.mkdir()
    env = {**os.environ, "COVERAGE_FILE": str(output / ".coverage")}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        *flags,
        "--cov",
        "--cov-report=term-missing",
        f"--cov-report=json:{output / 'coverage.json'}",
        f"--cov-report=xml:{output / 'coverage.xml'}",
        f"--junitxml={output / 'tests.xml'}",
    ]
    start = time.monotonic()
    with (output / "pytest.log").open("w") as log:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.monotonic() - start
    report = {"command": command, "seconds": elapsed, "exit_code": result.returncode}
    (output / "timing.json").write_text(json.dumps(report, indent=2) + "\n")
    result.check_returncode()
    cases(output / "tests.xml")
    with (output / "coverage-gates.log").open("w") as log:
        for gate in gates:
            command = [
                str(output / "coverage.json") if arg == "coverage.json" else arg
                for arg in gate
            ]
            subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
    report["coverage_gates"] = len(gates)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema": "apizr.pytest-benchmark/v1",
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "python": sys.version,
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "order": ["serial", "parallel"],
        "runs": {},
    }
    try:
        gates = coverage_gates()
        for name, flags in (("serial", ["-n", "0"]), ("parallel", PARALLEL)):
            print(f"Starting {name} full suite", flush=True)
            report["runs"][name] = measure(output / name, flags, gates)
        report["junit"] = compare(
            output / "serial/tests.xml", output / "parallel/tests.xml"
        )
        for name in ("serial", "parallel"):
            coverage = json.loads((output / name / "coverage.json").read_text())
            report["runs"][name]["coverage_totals"] = coverage["totals"]
        report["reduction"] = (
            1
            - report["runs"]["parallel"]["seconds"]
            / report["runs"]["serial"]["seconds"]
        )
        if report["reduction"] < 0.40:
            raise ValueError("Pytest duration reduction is below 40%")
        report["result"] = "pass"
    except Exception as exc:
        report["result"] = "fail"
        report["error"] = str(exc)
        raise
    finally:
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
