"""Require separate line and branch floors for selected execution evidence."""

import json
import sys
from pathlib import Path


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_bytes())
    summary = report["files"]["src/apizr/exposure/scope.py"]["summary"]
    for label, covered, total in (
        ("line", "covered_lines", "num_statements"),
        ("branch", "covered_branches", "num_branches"),
    ):
        percentage = 100 * summary[covered] / summary[total]
        print(f"Selected evidence {label} coverage: {percentage:.2f}%")
        if percentage < 95:
            raise ValueError(f"Selected evidence {label} coverage is below 95%")


if __name__ == "__main__":
    main()
