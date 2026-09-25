"""Prepare locked wheels, install isolated MCP plugin, exercise a real SDK client."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

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


def prepare(root: Path, python: str) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    house = root / "wheels"
    house.mkdir()
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
    plugin = next(house.glob("apizr_mcp-*.whl"))
    sha = hashlib.sha256(plugin.read_bytes()).hexdigest()
    run(
        [
            cli,
            "plugins",
            "install",
            plugin,
            "--sha256",
            sha,
            "--requirements",
            root / "plugin.lock",
            "--wheelhouse",
            house,
            "--plugins-dir",
            store,
        ],
        root,
    )
    shutil.copytree(REPO / "examples/project-config", root / "project")
    project = root / "project/apizr.toml"
    launch = [cli, "mcp", "serve", "--project", project, "--plugins-dir", store]
    assert run(launch, root, expected=2) == ""
    run(
        [
            cli,
            "plugins",
            "enable",
            "apizr-mcp",
            "--version",
            "0.0.0",
            "--plugins-dir",
            store,
        ],
        root,
    )
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
    for script in ("mcp_client_proof.py", "mcp_lifecycle_proof.py"):
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
