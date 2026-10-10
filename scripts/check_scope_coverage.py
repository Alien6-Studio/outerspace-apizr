"""Require separate line and branch floors for selected execution evidence."""

import json
import sys
from pathlib import Path


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_bytes())
    scopes = [
        ("Selected evidence", report["files"]["src/apizr/exposure/scope.py"]["summary"])
    ]
    for name in (
        "src/apizr/readiness/structured.py",
        "src/apizr/contracts/types.py",
        "src/apizr/contracts/lowering.py",
        "src/apizr/repository_views/model.py",
        "src/apizr/repository_views/projection.py",
        "plugins/mcp/src/apizr_mcp/model.py",
    ):
        scopes.append((name, report["files"][name]["summary"]))
    for name, function in (
        ("src/apizr/readiness/source.py", "SourceFacts.typing_marker"),
        ("src/apizr/interfaces/runtime.py", "validate_object"),
        ("plugins/mcp/src/apizr_mcp/worker.py", "calculate"),
        ("plugins/mcp/src/apizr_mcp/server.py", "error_result"),
        ("plugins/mcp/src/apizr_mcp/server.py", "create_server.call_tool"),
    ):
        scopes.append(
            (function, report["files"][name]["functions"][function]["summary"])
        )
    for name, data in sorted(report["files"].items()):
        if (
            name.startswith(
                ("src/apizr/plugins/preparation/", "src/apizr/experiments/")
            )
            and data["summary"]["num_statements"]
        ):
            summary = data["summary"]
            if summary["covered_lines"] != summary["num_statements"]:
                raise ValueError(f"{name} line coverage is below 100%")
            scopes.append((name, summary))
    comparison = report["files"]["src/apizr/experiments/comparison.py"]["summary"]
    if comparison["covered_branches"] < 0.98 * comparison["num_branches"]:
        raise ValueError("Experiment comparison branch coverage is below 98%")
    for name in ("exposure.py", "exposure_model.py"):
        bridge = report["files"]["src/apizr/experiments/" + name]["summary"]
        if bridge["covered_branches"] < 0.98 * bridge["num_branches"]:
            raise ValueError("Experiment exposure branch coverage is below 98%")
    scopes.append(
        (
            "Experiment exposure CLI",
            report["files"]["src/apizr/cli/commands/experiment_exposure.py"]["summary"],
        )
    )
    scopes.append(
        (
            "Experiment diff CLI",
            report["files"]["src/apizr/cli/commands/experiment.py"]["functions"][
                "_diff"
            ]["summary"],
        )
    )
    for scope, summary in scopes:
        for label, covered, total in (
            ("line", "covered_lines", "num_statements"),
            ("branch", "covered_branches", "num_branches"),
        ):
            percentage = (
                100 * summary[covered] / summary[total] if summary[total] else 100
            )
            print(f"{scope} {label} coverage: {percentage:.2f}%")
            if percentage < 95:
                raise ValueError(f"{scope} {label} coverage is below 95%")


if __name__ == "__main__":
    main()
