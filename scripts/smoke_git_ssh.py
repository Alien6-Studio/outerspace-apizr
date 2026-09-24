"""Prove SSH acquisition using a minimal wheel and disposable OpenSSH fixtures."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from git_ssh_fixture import server


def exercise(python: Path, cli: Path, work: Path) -> None:
    root = (work / "git-ssh-proof").resolve()
    root.mkdir()
    scratch = root / "scratch"
    scratch.mkdir()
    environment = {**os.environ, "TMPDIR": str(scratch)}
    with server(root / "server") as remote:
        (root / "readiness.json").write_text('{"execution":{"modes":["direct"]}}')
        (root / "exposure.json").write_text(
            json.dumps(
                {
                    "selection": {"include": ["python:calculator:add"]},
                    "interfaces": ["rest", "mcp"],
                    "execution": {"allowed": ["direct"]},
                }
            )
        )

        def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
            result = subprocess.run(
                [str(cli), *arguments],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
            assert not list(scratch.iterdir())
            return result

        remote_flags = [
            "--git",
            remote.url,
            "--ref",
            remote.commit,
            "--subdir",
            "service",
            "--ssh-agent-socket",
            str(remote.socket),
            "--ssh-known-hosts",
            str(remote.known_hosts),
        ]
        policies = ["--policy", "exposure.json", "--readiness-policy", "readiness.json"]
        for prefix, flags in [
            (["readiness"], ["--policy", "readiness.json", "--report"]),
            (["expose", "plan"], [*policies, "--plan"]),
        ]:
            actual = run([*prefix, *remote_flags, *flags])
            expected = run([*prefix, str(remote.source / "service"), *flags])
            assert actual.stdout == expected.stdout
            assert actual.stderr == f"Git snapshot: commit {remote.commit}\n"

        def files(path: Path) -> dict[str, bytes]:
            return {
                p.relative_to(path).as_posix(): p.read_bytes()
                for p in path.rglob("*")
                if p.is_file()
            }

        for interface in ("rest", "mcp"):
            for name, flags in [
                ("remote", remote_flags),
                ("local", [str(remote.source / "service")]),
            ]:
                run(
                    [
                        "expose",
                        "build",
                        interface,
                        *flags,
                        *policies,
                        "--output-dir",
                        f"{name}-{interface}",
                    ]
                )
            assert files(root / f"remote-{interface}") == files(
                root / f"local-{interface}"
            )
        docs = (
            Path(__file__).resolve().parents[1] / "docs/reference/git-ssh.md"
        ).read_text()
        example = docs.split("```python\n", 1)[1].split("```", 1)[0]
        guard = """import sys, importlib.metadata
def audit(event, args):
    if event == "import" and (args[0].split(".")[0] in {"fastapi", "mcp", "nbconvert", "uvicorn", "yaml", "questionary"} or args[0].endswith("_cli") or args[0].startswith("apizr.extensions.plugins")):
        raise AssertionError(args[0])
def forbidden(*args, **kwargs): raise AssertionError("plugin discovery")
sys.addaudithook(audit)
importlib.metadata.entry_points = forbidden
"""
        result = subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                guard
                + example
                + """
assert not snapshot.root.exists()
from apizr.repository_interfaces.runtime import load_bundle
for interface in ("rest", "mcp"):
    _, bindings, loader, _ = load_bundle(Path("python-" + interface), interface)
    try:
        assert bindings["python:calculator:add"](2, 3) == 5
    finally:
        loader.close()
""",
                remote.url,
                remote.commit,
                str(remote.socket),
                str(remote.known_hosts),
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert not list(scratch.iterdir())
        for interface in ("rest", "mcp"):
            assert files(root / f"python-{interface}") == files(
                root / f"local-{interface}"
            )
    print(
        "PASS Git SSH: isolated agent/server, minimal wheel, four CLI commands and documented Python API; parity after cleanup"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with TemporaryDirectory(prefix="apizr-ssh-wheel-") as directory:
        root = Path(directory)
        env = root / "env"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(env)], check=True, timeout=30
        )
        python = env / "bin/python"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel)],
            check=True,
            timeout=120,
        )
        exercise(python, env / "bin/apizr", root)


if __name__ == "__main__":
    main()
