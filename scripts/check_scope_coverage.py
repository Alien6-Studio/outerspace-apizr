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
    for scope, summary in scopes:
        for label, covered, total in (
            ("line", "covered_lines", "num_statements"),
            ("branch", "covered_branches", "num_branches"),
        ):
            percentage = 100 * summary[covered] / summary[total]
            print(f"{scope} {label} coverage: {percentage:.2f}%")
            if percentage < 95:
                raise ValueError(f"{scope} {label} coverage is below 95%")


if __name__ == "__main__":
    main()
