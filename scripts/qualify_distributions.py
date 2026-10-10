"""Qualify retained candidate bytes; isolate all pip/uv/pipx state from the user."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from coordinated_distributions import ROOT, digest, load, run, target_root, write
from smoke_extension_packaging import snapshot


def size(root: Path) -> int:
    return sum(
        path.stat().st_size
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def measure(command: list[str], cwd: Path, env: dict[str, str]) -> list[float]:
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        run(*command, cwd=cwd, env=env, timeout=30)
        samples.append(time.perf_counter() - started)
    return samples


def documented(name: str, cwd: Path, env: dict[str, str]) -> None:
    """Execute the installation page's shell block without rewriting its commands."""
    page = (ROOT / "docs/getting-started/install.md").read_text()
    blocks = dict(
        re.findall(r"<!-- install:([a-z]+) -->\s*```sh\n(.*?)```", page, re.S)
    )
    run("/bin/sh", "-c", "set -eu\n" + blocks[name], cwd=cwd, env=env)


def qualify(candidate: Path, target: Path, output: Path) -> None:
    manifest = load(candidate)
    os.environ["APIZR_RELEASE_SET"] = str(candidate)
    os.environ["APIZR_RELEASE_TARGET"] = str(target)
    assert target_root() == target
    output.mkdir(parents=True, exist_ok=False)
    core_wheel = next((candidate / "dist").glob("outerspace_apizr-*.whl"))
    results = {
        "commit": manifest["commit"],
        "candidate_sha256": digest(candidate / "candidate.json"),
        "target": json.loads((target / "target.json").read_text())["target"],
        "timing_definition": "five wall-clock subprocess samples; no extrapolation; includes interpreter startup",
        "download_definition": "sum of unique compressed wheel bytes; excludes tools and caches",
        "installed_definition": "regular file byte lengths, not allocated filesystem blocks",
        "measurements": {},
    }
    with tempfile.TemporaryDirectory(prefix="apizr-release-install-") as directory:
        root = Path(directory).resolve()
        env = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "UV_PYTHON_DOWNLOADS": "never",
            "UV_TOOL_DIR": str(root / "uv-tools"),
            "UV_TOOL_BIN_DIR": str(root / "uv-bin"),
            "PIPX_HOME": str(root / "pipx-home"),
            "PIPX_BIN_DIR": str(root / "pipx-bin"),
            "PIPX_MAN_DIR": str(root / "pipx-man"),
            "PIPX_DEFAULT_PYTHON": sys.executable,
        }
        env.pop("PYTHONPATH", None)
        env.pop("VIRTUAL_ENV", None)
        # pip bootstrapping is explicit test preparation, not plugin installation.
        env.update(
            APIZR_VERSION=manifest["version"],
            PYTHON=sys.executable,
            CORE_DIR=str(root / "pip"),
            CANDIDATE=str(candidate),
            TARGET=str(target),
        )
        documented("pip", root, env)
        python = root / "pip/bin/python"
        cli = root / "pip/bin/apizr"
        assert (
            run(cli, "--version", cwd=root, env=env).strip()
            == "outerspace-apizr " + manifest["version"]
        )
        run(
            python,
            "-I",
            "-B",
            "-c",
            "import importlib.util as u; assert all(u.find_spec(n) is None for n in ('mcp','uvicorn','fastapi','apizr_mcp','apizr_oci','apizr_attest'))",
            cwd=root,
            env=env,
        )
        before = snapshot(root / "pip")
        run(
            python,
            "-I",
            "-B",
            ROOT / "scripts/governance_evidence_proof.py",
            "--examples",
            ROOT / "examples/governance",
            "--output",
            output / "governance-evidence",
            cwd=root,
            env=env,
        )
        results["governance_evidence"] = "passed"
        run(
            python,
            "-I",
            "-B",
            ROOT / "scripts/experiment_contract_proof.py",
            "--fixtures",
            ROOT / "tests/fixtures/experiments/v1",
            "--output",
            output / "experiment-contracts.json",
            cwd=root,
            env=env,
        )
        results["experiment_contracts"] = "passed"
        run(
            python,
            "-I",
            "-B",
            ROOT / "scripts/experiment_inspection_proof.py",
            "--fixtures",
            ROOT / "tests/fixtures/experiments/inspection",
            "--output",
            output / "experiment-inspection-python.json",
            cwd=root,
            env=env,
        )
        results["experiment_inspection"] = "passed"
        run(
            python,
            "-I",
            "-B",
            ROOT / "scripts/experiment_run_proof.py",
            "--output",
            output / "experiment-run-python.json",
            cwd=root,
            env=env,
        )
        results["experiment_run"] = "passed"
        run(
            python,
            "-I",
            "-B",
            ROOT / "scripts/experiment_diff_proof.py",
            "--fixtures",
            ROOT / "tests/fixtures/experiments/comparison/v1",
            "--output",
            output / "experiment-diff.json",
            cwd=root,
            env=env,
        )
        results["experiment_diff"] = "passed"
        run(
            sys.executable,
            ROOT / "scripts/smoke_experiment_docs.py",
            cli,
            "--output",
            output / "experiment-docs.json",
            cwd=root,
            env=env,
        )
        results["experiment_docs"] = "passed"
        results["measurements"]["core"] = {
            "wheel_bytes": size(target / "base"),
            "installed_bytes": size(root / "pip"),
            "version_seconds": measure([str(cli), "--version"], root, env),
        }
        documented("uv", root, env)
        assert (
            run(root / "uv-bin/apizr", "--version", cwd=root, env=env)
            .strip()
            .endswith(manifest["version"])
        )
        # pipx is a prepared qualification tool, never injected into the core.
        run(
            "uv",
            "venv",
            "--python",
            sys.executable,
            root / "pipx-tool",
            cwd=root,
            env=env,
        )
        run(
            "uv",
            "pip",
            "install",
            "--python",
            root / "pipx-tool/bin/python",
            "pipx==1.8.0",
            cwd=root,
            env=env,
        )
        documented(
            "pipx",
            root,
            {**env, "PATH": str(root / "pipx-tool/bin") + os.pathsep + env["PATH"]},
        )
        assert (
            run(root / "pipx-bin/apizr", "--version", cwd=root, env=env)
            .strip()
            .endswith(manifest["version"])
        )
        for profile, names in (
            ("mcp", ("mcp",)),
            ("oci", ("oci",)),
            ("delivery", ("oci", "attest")),
        ):
            plan = root / (profile + "-plan")
            store = root / (profile + "-store")
            documented(
                "profile",
                root,
                {
                    **env,
                    "PROFILE": profile,
                    "PLAN": str(plan),
                    "PLUGINS_DIR": str(store),
                },
            )
            assert (
                json.loads(
                    run(
                        cli,
                        "plugins",
                        "list",
                        "--active",
                        "--json",
                        "--plugins-dir",
                        store,
                        cwd=root,
                        env=env,
                    )
                )["installations"]
                == []
            )
            for name in names:
                run(
                    cli,
                    "plugins",
                    "enable",
                    "outerspace-apizr-" + name,
                    "--version",
                    manifest["version"],
                    "--plugins-dir",
                    store,
                    cwd=root,
                    env=env,
                )
            active = json.loads(
                run(
                    cli,
                    "plugins",
                    "list",
                    "--active",
                    "--json",
                    "--plugins-dir",
                    store,
                    cwd=root,
                    env=env,
                )
            )["installations"]
            startup = {
                item["name"]: measure(
                    [
                        item["python"],
                        "-I",
                        "-B",
                        "-c",
                        "import importlib; importlib.import_module("
                        + repr(item["module"])
                        + ")",
                    ],
                    root,
                    env,
                )
                for item in active
            }
            wheels = {
                path.name: path.stat().st_size
                for name in names
                for path in (target / name).glob("*.whl")
            }
            results["measurements"][profile] = {
                "wheel_bytes": sum(wheels.values()),
                "installed_bytes": size(store),
                "inventory_seconds": measure(
                    [
                        str(cli),
                        "plugins",
                        "list",
                        "--active",
                        "--json",
                        "--plugins-dir",
                        str(store),
                    ],
                    root,
                    env,
                ),
                "module_startup_seconds": startup,
                "invocation": "qualified separately by real MCP/OCI/Attest proof; inventory timing is not invocation latency",
            }
        assert snapshot(root / "pip") == before, "Plugins changed the core"
        # Stable and development snippets exercise an actual PyPI 0.3.0 installation
        # alongside the retained candidate, without replacing the historical proof.
        with (output / "migration.log").open("w") as log:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/smoke_readme.py"),
                    str(cli),
                    "--development",
                    "--repository-refinement",
                ],
                cwd=root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=600,
            )
    # Native Git prerequisites and all historical extras use this retained wheel.
    with (output / "installations.log").open("w") as log:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/smoke_installations.py"),
                str(core_wheel),
                "--proof-output",
                str(output),
            ],
            env=os.environ,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=900,
        )
    results.update(
        {
            "pip": "passed",
            "uv_tool": "passed",
            "pipx": "passed",
            "core_unchanged": True,
            "catalog_resolve_lock_sync": "passed",
            "migration": "passed",
            "extras_local_https_ssh": "passed",
        }
    )
    write(output / "qualification.json", results)
    shutil.copyfile(candidate / "candidate.json", output / "candidate.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    qualify(args.candidate.resolve(), args.target.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
