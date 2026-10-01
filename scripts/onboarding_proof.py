"""Installed-wheel onboarding outside checkout and real native shell completion."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from smoke_extension_packaging import snapshot

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd, *, expected=0, env=None):
    result = subprocess.run(
        list(map(str, args)),
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == expected, (args, result.stdout, result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-shells", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    run(["uv", "build", "--wheel", ROOT, "--out-dir", root / "wheels"], root)
    wheel = next((root / "wheels").glob("*.whl"))
    run(["uv", "venv", "--python", sys.executable, root / "env"], root)
    python = root / "env/bin/python"
    run(["uv", "pip", "install", "--python", python, wheel], root)
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": str(root / "env/bin") + os.pathsep + os.environ["PATH"],
    }
    cli = [python, "-I", "-B", "-m", "apizr.cli"]
    run(
        [
            python,
            "-I",
            "-B",
            "-c",
            "from importlib.metadata import requires;from importlib.util import find_spec;assert [x for x in requires('outerspace-apizr') if 'extra ==' not in x]==['pydantic<3,>=2.12'];assert find_spec('yaml') is None;assert find_spec('mcp') is None",
        ],
        root,
        env=env,
    )
    project = root / "project"
    project.mkdir()
    (project / "sample.py").write_text(
        "def add(a: int, b: int = 2) -> int:\n    return a + b\n"
    )
    init = json.loads(run([*cli, "init", project, "--json"], root, env=env))
    base = [
        "--project",
        project / "apizr.toml",
        "--operator-policy",
        project / ".apizr/operator.json",
    ]
    before = snapshot(project)
    start = time.perf_counter()
    report = json.loads(run([*cli, "doctor", *base, "--json"], root, env=env))
    elapsed = time.perf_counter() - start
    assert not any(c["status"] == "fail" for c in report["checks"])
    minimal = json.loads(
        run(
            [*cli, "doctor", *base, "--profile", "clients", "--json"],
            root,
            expected=1,
            env=env,
        )
    )
    assert any(
        c["code"] == "clients_extra_available" and c["status"] == "fail"
        for c in minimal["checks"]
    )
    assert snapshot(project) == before
    readonly = json.loads(
        run(
            [python, "-I", "-B", ROOT / "scripts/doctor_readonly_proof.py", *base],
            root,
            env=env,
        )
    )
    catalog = json.loads(
        run(
            [
                *cli,
                "scan",
                project,
                "--operator-policy",
                project / ".apizr/operator.json",
                "--catalog",
            ],
            root,
            env=env,
        )
    )
    readiness = json.loads(run([*cli, "readiness", *base, "--report"], root, env=env))
    policy = project / ".apizr/policies/exposure.json"
    exposure = json.loads(policy.read_text())
    assert (
        not exposure["selection"]["include"]
        and not exposure["selection"]["include_all_ready"]
    )
    exposure["selection"]["include"] = ["python:sample:add"]
    policy.write_text(json.dumps(exposure))
    for interface in ("rest", "mcp"):
        run(
            [
                *cli,
                "expose",
                "build",
                interface,
                *base,
                "--output-dir",
                root / interface,
            ],
            root,
            env=env,
        )
        assert (root / interface / f"apizr-repository-{interface}.json").is_file()
    run(["uv", "pip", "install", "--python", python, str(wheel) + "[clients]"], root)
    before = snapshot(project), snapshot(root / "rest")
    client = json.loads(
        run(
            [
                *cli,
                "doctor",
                *base,
                "--profile",
                "clients",
                "--bundle",
                root / "rest",
                "--json",
            ],
            root,
            env=env,
        )
    )
    assert not any(c["status"] == "fail" for c in client["checks"])
    assert (snapshot(project), snapshot(root / "rest")) == before
    shells = {}
    for shell in ("bash", "zsh", "fish"):
        output = run([*cli, "completion", shell], root, env=env)
        assert output == run([*cli, "completion", shell], root, env=env)
        assert str(root) not in output
        path = root / f"apizr.{shell}"
        path.write_text(output)
        binary = shutil.which(shell)
        if binary is None:
            assert not args.require_shells, f"{shell} required"
            shells[shell] = "rendered; real shell required in Linux qualification"
            continue
        run([binary, "-n", path], root, env=env)
        if shell == "bash":
            command = 'source "$1"; COMP_WORDS=(apizr doctor --profile ""); COMP_CWORD=3; _apizr_complete; printf "%s\\n" "${COMPREPLY[@]}"'
        elif shell == "zsh":
            command = 'compdef() { :; }; compadd() { shift; print -l -- "$@"; }; source "$1"; words=(apizr doctor --profile ""); CURRENT=4; _apizr'
        else:
            command = 'source $argv[1]; complete -C "apizr doctor --profile "'
        reply = run(
            [binary, "-c", command, *([path] if shell == "fish" else ["proof", path])],
            root,
            env=env,
        )
        assert {v.split("\t")[0] for v in reply.splitlines()} == {
            "core",
            "mcp",
            "oci",
            "delivery",
            "clients",
        }, reply
        shells[shell] = "syntax and installed-backend candidates passed"
    start = time.perf_counter()
    reply = run(
        [*cli, "__complete", "--", "clients", "export", "--format", ""], root, env=env
    )
    completion_time = time.perf_counter() - start
    assert set(reply.splitlines()) == {"postman", "bruno", "insomnia"}
    result = {
        "source_sha": run(["git", "rev-parse", "HEAD"], ROOT).strip(),
        "wheel_bytes": wheel.stat().st_size,
        "outside_checkout": True,
        "minimal_pydantic_only": True,
        "init": init,
        "doctor": report,
        "readonly": readonly,
        "clients": client,
        "shells": shells,
        "timings_seconds": {
            "doctor_process": elapsed,
            "completion_process": completion_time,
        },
        "scan_schema": catalog.get("schema_version"),
        "readiness_schema": readiness.get("schema_version"),
        "rest_and_mcp_generated": True,
    }
    (root / "onboarding-proof.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
