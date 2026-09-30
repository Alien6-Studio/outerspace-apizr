"""Prepare locked wheels, install isolated MCP plugin, exercise a real SDK client."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from coordinated_distributions import copy_closure
from operator_policy_proof import write_analysis_policy
from smoke_extension_packaging import snapshot
from smoke_oci_plugin import lock_wheels

REPO = Path(__file__).resolve().parents[1]


def run(args, cwd, *, timeout=180, expected=0, env=None):
    result = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env if env is not None else {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != expected:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def prepare_wheels(root: Path, python: str, house: Path) -> None:
    """Reuse the exact locked MCP closure for installed stdio and delivery proofs."""
    house.mkdir()
    if not copy_closure("mcp", house):
        run(["uv", "build", "--wheel", REPO, "--out-dir", house], root)
        run(["uv", "build", "--wheel", REPO / "plugins/mcp", "--out-dir", house], root)
        run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--extra",
                "mcp",
                "--no-emit-project",
                "--output-file",
                root / "dependencies.txt",
            ],
            REPO,
        )
        run(
            [
                "uv",
                "venv",
                "--seed",
                "--no-python-downloads",
                "--python",
                python,
                root / "prepare",
            ],
            root,
        )
        run(
            [
                root / "prepare/bin/python",
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--dest",
                house,
                "-r",
                root / "dependencies.txt",
            ],
            root,
        )


def prepare(root: Path, python: str) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    house = root / "wheels"
    prepare_wheels(root, python, house)
    lock_wheels(house, root / "plugin.lock")
    core_wheel = next(house.glob("outerspace_apizr-*.whl"))
    for name, requirements in [
        ("core", [core_wheel]),
        ("client", [core_wheel, "mcp==2.2.0"]),
    ]:
        run(
            ["uv", "venv", "--no-python-downloads", "--python", python, root / name],
            root,
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                root / name / "bin/python",
                "--offline",
                "--no-index",
                "--find-links",
                house,
                *requirements,
            ],
            root,
        )
    before = snapshot(root / "core")
    cli = root / "core/bin/apizr"
    store = root / "plugins"
    # Keep MCP's already prepared closure; OCI/Attest have separate minimal closures.
    import zipfile
    from email.parser import BytesParser

    core_names = set(
        json.loads(
            run(
                [
                    root / "core/bin/python",
                    "-I",
                    "-B",
                    "-c",
                    "import importlib.metadata as m,json;print(json.dumps([d.metadata['Name'].lower().replace('_','-') for d in m.distributions()]))",
                ],
                root,
            )
        )
    )
    minimal = root / "minimal-wheels"
    minimal.mkdir()
    for wheel in house.glob("*.whl"):
        with zipfile.ZipFile(wheel) as archive:
            metadata = BytesParser().parsebytes(
                archive.read(
                    next(
                        n
                        for n in archive.namelist()
                        if n.endswith(".dist-info/METADATA")
                    )
                )
            )
        if metadata["Name"].lower().replace("_", "-") in core_names:
            shutil.copyfile(wheel, minimal / wheel.name)
    for plugin_name in ("oci", "attest"):
        if not copy_closure(plugin_name, minimal):
            run(
                [
                    "uv",
                    "build",
                    "--wheel",
                    REPO / "plugins" / plugin_name,
                    "--out-dir",
                    minimal,
                ],
                root,
            )
        lock_wheels(minimal, root / (plugin_name + ".lock"))
    for wheel in minimal.glob("*.whl"):
        destination = house / wheel.name
        if not destination.exists():
            shutil.copyfile(wheel, destination)
    commit = run(["git", "rev-parse", "HEAD"], REPO).strip()
    catalog = root / "catalog"
    run(
        [
            root / "core/bin/python",
            "-I",
            "-B",
            REPO / "scripts/catalog_plugin_plan.py",
            "--wheelhouse",
            house,
            "--plugin",
            "outerspace-apizr-mcp=" + str(root / "plugin.lock"),
            "--plugin",
            "outerspace-apizr-oci=" + str(root / "oci.lock"),
            "--plugin",
            "outerspace-apizr-attest=" + str(root / "attest.lock"),
            "--commit",
            commit,
            "--output",
            catalog,
            "--profile",
            "mcp",
        ],
        root,
    )
    plan = catalog / "plan"
    run(
        [
            cli,
            "plugins",
            "lock",
            "check",
            "--project",
            plan / "apizr.toml",
            "--lock",
            plan / "apizr.plugins.lock.json",
            "--wheelhouse",
            house,
            "--json",
        ],
        root,
    )
    assert not store.exists() and snapshot(root / "core") == before
    run(
        [
            cli,
            "plugins",
            "sync",
            "--project",
            plan / "apizr.toml",
            "--lock",
            plan / "apizr.plugins.lock.json",
            "--wheelhouse",
            house,
            "--plugins-dir",
            store,
            "--json",
        ],
        root,
    )
    assert not json.loads(
        run(
            [cli, "plugins", "list", "--active", "--json", "--plugins-dir", store], root
        )
    )["installations"]
    shutil.copytree(REPO / "examples/project-config", root / "project")
    project = root / "project/apizr.toml"
    authority = write_analysis_policy(root / "operator.json", project.parent)
    launch = [
        cli,
        "mcp",
        "serve",
        "--project",
        project,
        "--operator-policy",
        authority,
        "--plugins-dir",
        store,
    ]
    assert run(launch, root, expected=2) == ""
    run(
        [
            cli,
            "plugins",
            "enable",
            "outerspace-apizr-mcp",
            "--version",
            "0.4.2rc1",
            "--plugins-dir",
            store,
        ],
        root,
    )
    # Source refusal is checked before launching the active MCP installation.
    denied = subprocess.run(
        [
            str(cli),
            "mcp",
            "serve",
            "--project",
            str(project),
            "--plugins-dir",
            str(store),
        ],
        cwd=root,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        input=b"",
        capture_output=True,
        timeout=10,
    )
    assert denied.returncode == 2 and not denied.stdout
    assert json.loads(denied.stderr)["code"] == "operator_policy_required"
    inventory = json.loads(
        run([cli, "plugins", "list", "--json", "--plugins-dir", store], root)
    )
    record = inventory["installations"][0]
    run(
        [
            root / "core/bin/python",
            "-I",
            "-B",
            "-c",
            "import importlib.util as u; assert all(u.find_spec(n) is None for n in ('mcp','apizr_mcp','fastapi'))",
        ],
        root,
    )
    assert snapshot(root / "core") == before
    (root / "core-before.json").write_text(json.dumps(before))
    (root / "activation-before.json").write_bytes(
        (store / "activations.json").read_bytes()
    )
    return {
        "cli": str(cli),
        "plugin_python": record["python"],
        "project": str(project),
        "operator_policy": str(authority),
        "store": str(store),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    root = args.output.resolve()
    config = prepare(root, args.python)
    (root / "installed.json").write_text(json.dumps(config))
    for script in (
        "mcp_client_proof.py",
        "mcp_delivery_local_proof.py",
        "mcp_lifecycle_proof.py",
    ):
        result = subprocess.run(
            [root / "client/bin/python", REPO / "scripts" / script, root],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=240,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        (root / (script + ".log")).write_text(result.stdout + result.stderr)
        print(result.stdout)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
    assert snapshot(root / "core") == json.loads(
        (root / "core-before.json").read_text()
    )
    assert (root / "activation-before.json").read_bytes() == (
        root / "plugins/activations.json"
    ).read_bytes()
    (root / "outcome.json").write_text(
        json.dumps(
            {"success": True, "core_unchanged": True, "activations_unchanged": True}
        )
    )


if __name__ == "__main__":
    main()
