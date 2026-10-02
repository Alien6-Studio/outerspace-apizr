"""Original-wheel, minimal-core proof outside checkout; no forge runtime emulation."""

import argparse
import hashlib
import json
import os
import runpy
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Runs inside the installed, isolated core environment, outside this checkout.
INSTALLED_PROOF = r"""
import json, sys
from importlib.metadata import requires, version
from importlib.util import find_spec
from pathlib import Path
from apizr.ci import execute
from apizr.ci.runner import analysis_authority
from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy, plan_bytes
from apizr.project import load_project
from apizr.repository_readiness import RepositoryReadinessPolicy, report_bytes
assert version("outerspace-apizr") == "0.4.2rc2"
assert [r for r in requires("outerspace-apizr") if "extra ==" not in r] == ["pydantic<3,>=2.12"]
for name in ("yaml", "mcp", "fastapi", "apizr_oci", "apizr_attest", "apizr_mcp"):
    assert find_spec(name) is None, name
project = Path("project/apizr.toml")
config = load_project(project)
p = prepare_exposure(config.root, operator_policy=analysis_authority(config.root),
    policy=ExposurePolicy.model_validate_json(config.exposure_policy.read_bytes()),
    readiness_policy=RepositoryReadinessPolicy.model_validate_json(config.readiness_policy.read_bytes()),
    scan_policy=config.scan, graph_policy=config.graph, application=config.application)
def tree(root):
    return {f.relative_to(root).as_posix(): f.read_bytes() for f in root.rglob("*") if f.is_file()}
for operation in ("check", "build-rest", "build-mcp"):
    out = Path("api-" + operation)
    assert execute(operation, project=project, output_dir=out, authorize_project_analysis=True).exit_code == 0
    assert (out/"readiness.json").read_bytes() == report_bytes(p.readiness)
    assert (out/"exposure-plan.json").read_bytes() == plan_bytes(p.plan)
    if operation != "check":
        assert tree(out/"bundle") == render_bundle(p, interface=operation[6:])
    assert tree(out) == tree(Path("cli-" + operation))
    if len(sys.argv) > 1:
        assert tree(out) == tree(Path(sys.argv[1]) / (".apizr-ci-" + operation))
"""


def run(command, root, env, expected=0):
    result = subprocess.run(
        list(map(str, command)),
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == expected, (
        result.returncode,
        result.stdout,
        result.stderr,
    )
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-root", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    assert not root.is_relative_to(ROOT), "Installed proof must be outside checkout"
    adapter = runpy.run_path(str(ROOT / ".github/actions/forge/run.py"))
    name, raw = adapter["wheel_bytes"](str(args.wheel), args.sha256, "0.4.2rc2")
    root.mkdir(parents=True, exist_ok=False)
    wheel = root / name
    wheel.write_bytes(raw)
    shutil.copytree(ROOT / "tests/fixtures/forge/project", root / "project")
    environment = {
        "PATH": os.environ["PATH"],
        "HOME": str(root),
        "PIP_CONFIG_FILE": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    venv.EnvBuilder(with_pip=True).create(root / "environment")
    python = root / "environment/bin/python"
    cli = root / "environment/bin/apizr"
    run(
        [
            python,
            "-I",
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--index-url",
            "https://pypi.org/simple",
            wheel,
        ],
        root,
        environment,
    )
    assert (
        run([cli, "--version"], root, environment).strip()
        == "outerspace-apizr 0.4.2rc2"
    )
    environment.update(
        GITHUB_TOKEN="SECRET_GITHUB_SENTINEL", CI_JOB_TOKEN="SECRET_GITLAB_SENTINEL"
    )
    for operation in ("check", "build-rest", "build-mcp"):
        run(
            [
                cli,
                "ci",
                operation,
                "--project",
                "project/apizr.toml",
                "--authorize-project-analysis",
                "--output-dir",
                "cli-" + operation,
            ],
            root,
            environment,
        )
    command = [python, "-I", "-c", INSTALLED_PROOF]
    if args.compare_root:
        command.append(str(args.compare_root.resolve()))
    run(command, root, environment)
    for output in root.glob("cli-*"):
        for file in output.rglob("*"):
            if file.is_file():
                raw_artifact = file.read_bytes()
                for forbidden in (b"SECRET_", str(root).encode(), str(ROOT).encode()):
                    assert forbidden not in raw_artifact
    evidence = {
        "schema": "apizr.forge-proof/v1",
        "wheel_sha256": hashlib.sha256(raw).hexdigest(),
        "version": "0.4.2rc2",
        "python": sys.version.split()[0],
        "minimal_core": True,
        "installed_outside_checkout": True,
        "api_cli_byte_parity": True,
        "action_byte_parity": bool(args.compare_root),
        "operations": ["check", "build-rest", "build-mcp"],
        "gitlab_hosted_runtime": "not executed — no GitLab component project authorized",
    }
    (root / "forge-proof.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
