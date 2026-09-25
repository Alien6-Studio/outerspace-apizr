"""Fixed generated-MCP recovery qualification; preserve every outcome, no retries."""

import argparse
import json
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPETITIONS = 10
TEST = "tests/governed/test_transports.py::test_real_governed_mcp_survives_failures"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    summary = {
        "python": sys.version,
        "executable": sys.executable,
        "architecture": platform.machine(),
        "platform": platform.platform(),
        "repetitions": REPETITIONS,
        "test": TEST,
        "results": results,
    }
    for iteration in range(1, REPETITIONS + 1):
        name = f"iteration-{iteration:03}"
        report = output / f"{name}.xml"
        with (output / f"{name}.log").open("w") as log:
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "--no-cov",
                        TEST,
                        f"--junitxml={report}",
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=150,
                    check=False,
                )
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = "timeout"
        counts = {}
        try:
            for suite in ET.parse(report).getroot().iter("testsuite"):
                for key in ("tests", "failures", "errors", "skipped"):
                    counts[key] = counts.get(key, 0) + int(suite.attrib[key])
            if code == 0 and (
                counts.get("tests") != 2
                or any(counts.get(key, 0) for key in ("failures", "errors", "skipped"))
            ):
                code = "incomplete_report"
        except (OSError, ValueError, ET.ParseError):
            if code == 0:
                code = "missing_report"
        results.append({"iteration": iteration, "exit_code": code, "counts": counts})
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{name}: {code}", flush=True)
    return int(any(result["exit_code"] != 0 for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
