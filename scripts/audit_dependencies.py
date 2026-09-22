"""Audit the resolved uv graph by scope; every finding or collection error blocks."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCOPES = {
    "runtime": ["--no-default-groups"],
    "runtime-notebook": ["--no-default-groups", "--extra", "notebook"],
    "runtime-http": ["--no-default-groups", "--extra", "http"],
    "runtime-mcp": ["--no-default-groups", "--extra", "mcp"],
    "runtime-legacy": ["--no-default-groups", "--extra", "legacy"],
    "development": ["--only-group", "dev"],
    "documentation": ["--only-group", "docs"],
    "security-tooling": ["--only-group", "security"],
}


def export_scope(root: Path, directory: Path, scope: str) -> Path:
    """Keep all Python/platform variants in the selected lockfile dependency group."""
    directory.mkdir(parents=True, exist_ok=True)
    lockfile = directory / "pylock.toml"
    subprocess.run(
        [
            "uv",
            "export",
            "--locked",
            "--offline",
            *SCOPES[scope],
            "--no-emit-project",
            "--format",
            "pylock.toml",
            "--output-file",
            str(lockfile),
        ],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return lockfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write all scope reports as JSON")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    reports = {}
    with tempfile.TemporaryDirectory(prefix="apizr-audit-") as directory:
        for scope in SCOPES:
            scoped = Path(directory) / scope
            export_scope(root, scoped, scope)
            report_path = scoped / "audit.json"
            print(f"Auditing {scope} dependencies", flush=True)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_audit",
                    "--locked",
                    str(scoped),
                    "--strict",
                    "--progress-spinner",
                    "off",
                    "--format",
                    "json",
                    "--output",
                    str(report_path),
                ],
                check=False,
            )
            if not report_path.is_file():
                raise RuntimeError(
                    f"pip-audit produced no report for {scope} (exit {result.returncode})"
                )
            report = json.loads(report_path.read_text())
            reports[scope] = {"exit_code": result.returncode, "report": report}
            dependencies = report.get("dependencies", [])
            findings = {
                (dep["name"], dep["version"], vulnerability["id"])
                for dep in dependencies
                for vulnerability in dep.get("vulns", [])
            }
            print(
                f"{scope}: {len(dependencies)} resolved entries, {len(findings)} distinct findings, exit {result.returncode}"
            )
            for name, version, advisory in sorted(findings):
                print(f"  {name}=={version}: {advisory}")
    if args.output:
        args.output.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    return 1 if any(report["exit_code"] != 0 for report in reports.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
