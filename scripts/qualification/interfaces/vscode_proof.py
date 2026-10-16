"""Exercise the real VS Code extension host against an explicitly selected engine."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from scripts.qualification.experiments.experiment_jupyter_proof import Kernel

ROOT = Path(__file__).resolve().parents[3]


def command(arguments, *, cwd, env=None, timeout=180):
    result = subprocess.run(
        list(map(str, arguments)),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            f"Qualification command failed ({result.returncode}): {result.stdout[-4096:]}\n{result.stderr[-4096:]}"
        )
    return result.stdout


def prepare(root, python):
    origin = json.loads(
        command(
            [
                python,
                "-I",
                "-B",
                "-c",
                "import apizr,json;from pathlib import Path;print(json.dumps(str(Path(apizr.__file__).resolve())))",
            ],
            cwd=root,
        )
    )
    project = root / "project"
    shutil.copytree(ROOT / "examples/data-science/fraud-detection", project)
    shutil.copyfile(
        ROOT / "examples/tracking/jupyter-capture.ipynb",
        project / "jupyter_capture.ipynb",
    )
    (project / "model.py").write_text("rate = 0.25\nscore = 0.75\n")
    (project / "inspect_only.py").write_text(
        'raise RuntimeError("Inspection must never execute this source")\n\ndef predict(value: float) -> float:\n    return value * 2\n'
    )
    (project / "apizr.toml").write_text('schema_version = "apizr.project/v1"\n')
    policy = root / "operator.json"
    policy.write_text(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": {"kind": "local", "root": str(project)},
                        "permissions": ["source.analyze"],
                    },
                    {
                        "adapter": "experiments",
                        "operation": "history.read",
                        "target": {"kind": "local", "root": str(project)},
                        "store": ".apizr/experiments/v1",
                        "permissions": ["experiments.read"],
                    },
                ],
            }
        )
    )
    incompatible = root / "incompatible-engine"
    incompatible.write_text(
        f"#!{python}\nimport json,sys\nassert '--project' not in sys.argv\nr=json.load(sys.stdin)\nprint(json.dumps(dict(schema_version='apizr.editor-response/v1',request_id=r['request_id'],operation=r['operation'],ok=True,value=dict(schema_version='apizr.editor-capabilities/v1',protocol='incompatible'),diagnostics=[])))\n"
    )
    incompatible.chmod(0o700)
    base = [python, "-I", "-B", "-m", "apizr.cli", "experiment"]
    env = {**os.environ, "APIZR_TELEMETRY": "0"}
    command(
        [*base, "run", "model.py", "--root", project, "--format", "json"],
        cwd=project,
        env=env,
    )
    code = "from pathlib import Path\nfrom apizr import tracking\nwith tracking.session(root=Path.cwd(), source='model.py'):\n    tracking.log_parameter('large_integer', 9223372036854775807)\n    tracking.log_parameter('rate', 0.2)\n    tracking.log_metric('score', 0.8)\n"
    command([python, "-I", "-B", "-c", code], cwd=project, env=env)
    kernel = Kernel(project, python=python)
    try:
        kernel.execute(
            "from pathlib import Path\nfrom apizr import tracking\nwith tracking.session(root=Path.cwd(), source='jupyter_capture.ipynb'):\n    tracking.log_parameter('rate', 0.3)\n    tracking.log_metric('score', 0.9)",
            "vscode-qualified-cell",
        )
    finally:
        kernel.close()
    fixture = {
        "python": str(python),
        "project": str(project),
        "policy": str(policy),
        "engine_origin": origin,
        "outside_checkout": not Path(origin).is_relative_to(ROOT),
        "inspections": {},
    }
    for name in ("inspect_only.py", "fraud_detection.ipynb", "jupyter_capture.ipynb"):
        fixture["inspections"][name] = json.loads(
            command(
                [*base, "inspect", name, "--root", project, "--format", "json"],
                cwd=project,
                env=env,
            )
        )
    fixture["history"] = json.loads(
        command(
            [
                python,
                "-I",
                "-B",
                "-c",
                "from pathlib import Path; from apizr.experiments.history import list_runs; print(list_runs(Path('.apizr/experiments/v1'), include_values=True).model_dump_json())",
            ],
            cwd=project,
            env=env,
        )
    )
    fixture["records"] = {
        item["run_digest"]: json.loads(
            command(
                [*base, "show", item["run_digest"], "--format", "json"],
                cwd=project,
                env=env,
            )
        )
        for item in fixture["history"]["runs"]
    }
    ids = list(fixture["records"])
    fixture["diff"] = json.loads(
        command(
            [*base, "diff", ids[0], ids[1], "--format", "json"], cwd=project, env=env
        )
    )
    (root / "fixtures.json").write_text(json.dumps(fixture, indent=2) + "\n")
    return project, policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-python", type=Path, required=True)
    parser.add_argument("--engine-executable", type=Path)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vsix", type=Path)
    parser.add_argument("--previous-vsix", type=Path)
    parser.add_argument("--untrusted", action="store_true")
    parser.add_argument(
        "--allow-checkout",
        action="store_true",
        help="Development proof only; retained engine qualification must use an installed wheel",
    )
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    python = args.engine_python.absolute()
    project, policy = prepare(root, python)
    fixture = json.loads((root / "fixtures.json").read_text())
    if not args.allow_checkout:
        assert fixture["outside_checkout"], (
            "Qualify the installed candidate wheel outside the checkout"
        )
    from scripts.qualification.interfaces.python_network_guard import guarded_engine

    with guarded_engine(python, root / "engine-network.log") as network:
        proof = run_host(args, root, python, project, policy)
    assert (
        network["apizr_processes"] == 0
        if args.untrusted
        else network["apizr_processes"] > 0
    )
    proof["offline_python_engine"] = network
    (root / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(proof))


def run_host(args, root, python, project, policy):
    profile, extensions = root / "profile", root / "extensions"
    (profile / "User").mkdir(parents=True)
    extensions.mkdir()
    settings = {
        "update.mode": "none",
        "extensions.autoUpdate": False,
        "extensions.autoCheckUpdates": False,
        "telemetry.telemetryLevel": "off",
        "workbench.startupEditor": "none",
        "security.workspace.trust.startupPrompt": "never",
        "apizr.engine.mode": "executable" if args.engine_executable else "python",
        "apizr.engine.python": str(python),
        "apizr.engine.executable": str(args.engine_executable.absolute())
        if args.engine_executable
        else "",
        "apizr.workspace.project": str(project / "apizr.toml"),
        "apizr.operatorPolicy": str(policy),
        "apizr.telemetry.enabled": False,
    }
    (profile / "User/settings.json").write_text(json.dumps(settings))
    code = args.code.resolve()
    common = [code, "--user-data-dir", profile, "--extensions-dir", extensions]
    if args.vsix:
        if args.previous_vsix:
            command(
                [
                    *common,
                    "--install-extension",
                    args.previous_vsix.absolute(),
                    "--force",
                ],
                cwd=root,
            )
            assert "alien6-studio.apizr@0.4.5" in command(
                [*common, "--list-extensions", "--show-versions"], cwd=root
            )
        command(
            [*common, "--install-extension", args.vsix.absolute(), "--force"], cwd=root
        )
        development = ROOT / "editors/vscode/test/driver"
    else:
        development = ROOT / "editors/vscode"
    host = code
    candidates = [code.parent.parent / "code"]
    if len(code.parents) > 3:
        candidates.insert(0, code.parents[3] / "MacOS/Code")
    for candidate in candidates:
        if candidate.is_file() and candidate != code:
            host = candidate
            break
    arguments = [
        *common,
        project,
        "--new-window",
        "--skip-welcome",
        "--skip-release-notes",
        "--disable-updates",
        "--disable-telemetry",
        "--extensionDevelopmentPath=" + str(development),
        "--extensionTestsPath=" + str(ROOT / "editors/vscode/test/host.cjs"),
    ]
    arguments[0] = host
    if not args.untrusted:
        arguments.append("--disable-workspace-trust")
    if sys.platform.startswith("linux"):
        # Disposable Xvfb qualification only, with a trusted extension/fixture.
        arguments.extend(("--no-sandbox", "--disable-gpu"))
    env = {
        **os.environ,
        "APIZR_VSCODE_PROOF": str(root),
        "APIZR_VSCODE_UNTRUSTED": "1" if args.untrusted else "0",
        "APIZR_TELEMETRY_CONFIG": str(root / "consent.json"),
    }
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env.pop("VSCODE_IPC_HOOK_CLI", None)
    result = subprocess.run(
        list(map(str, arguments)),
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    (root / "host.stdout.log").write_text(result.stdout)
    (root / "host.stderr.log").write_text(result.stderr)
    assert result.returncode == 0, f"Extension host failed; inspect {root}/host.*.log"
    proof_path = root / "proof.json"
    deadline = time.monotonic() + 60
    while not proof_path.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    proof = json.loads(proof_path.read_text())
    assert proof["result"] == "pass"
    if args.vsix:
        command([*common, "--uninstall-extension", "alien6-studio.apizr"], cwd=root)
        installed = command([*common, "--list-extensions"], cwd=root)
        assert "alien6-studio.apizr" not in installed
        assert not (profile / "User/globalStorage/alien6-studio.apizr").exists()
        proof["installed_vsix"] = args.vsix.name
        proof["uninstalled_without_owned_storage"] = True
        proof["upgraded_qualification_fixture"] = args.previous_vsix is not None
        (root / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    return proof


if __name__ == "__main__":
    main()
