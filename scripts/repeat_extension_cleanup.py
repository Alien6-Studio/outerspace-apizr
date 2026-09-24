"""Run a fixed cleanup regression series; retain every outcome, never retry to green."""

import argparse
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS = [
    "tests/extension_runtime/test_cleanup.py",
    "tests/extension_runtime/test_invocation.py::test_ordinary_child_holding_streams_is_killed",
    "tests/extension_runtime/test_invocation.py::test_timeout_cleans_group_including_ordinary_child",
    "tests/extension_runtime/test_invocation.py::test_detached_child_does_not_hold_host_forever",
]


GIT_WORKER_TESTS = [
    "tests/git_source/test_cleanup.py",
    *[
        "tests/git_source/test_ssh.py::test_authentication_refusals_clean_and_recover["
        + case
        + "]"
        for case in ("unknown", "changed", "revoked")
    ],
    "tests/execution/test_process.py::test_ordinary_descendant_is_stopped_with_worker",
    "tests/execution/test_process.py::test_descendant_fixture_cleans_failed_preparation",
    "tests/repository_execution/test_cleanup.py",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=25, choices=range(1, 101))
    parser.add_argument(
        "--suite", choices=("extension", "git-worker"), default="extension"
    )
    args = parser.parse_args()
    tests = GIT_WORKER_TESTS if args.suite == "git-worker" else TESTS
    expected_tests = 9 if args.suite == "git-worker" else 7
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, object]] = []
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "repetitions": args.repetitions,
        "tests": tests,
        "results": results,
    }
    for iteration in range(1, args.repetitions + 1):
        name = f"iteration-{iteration:03}"
        with (output / f"{name}.log").open("w") as log:
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "--no-cov",
                        *tests,
                        f"--junitxml={output / (name + '.xml')}",
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=120,
                    check=False,
                )
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        counts: dict[str, int] = {}
        try:
            suites = ET.parse(output / f"{name}.xml").getroot().iter("testsuite")
            for suite in suites:
                for key in ("tests", "failures", "errors", "skipped"):
                    counts[key] = counts.get(key, 0) + int(suite.attrib[key])
            if code == 0 and (
                counts.get("tests", 0) != expected_tests
                or any(counts.get(key, 0) for key in ("failures", "errors", "skipped"))
            ):
                code = "incomplete_report"
        except (OSError, ValueError, ET.ParseError):
            if code == 0:
                code = "missing_report"
        results.append({"iteration": iteration, "exit_code": code, "counts": counts})
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {code}", flush=True)
    return int(any(result["exit_code"] != 0 for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
