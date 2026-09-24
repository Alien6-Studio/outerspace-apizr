"""Prove HTTPS Git input using the minimal wheel outside its checkout."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from git_https_fixture import handler, repository, trusted_git
from https_fixture import certificate, https_server


def exercise(python: Path, cli: Path, work: Path) -> None:
    root = work / "git-proof"
    root.mkdir()
    cert, key = certificate(root)
    source, commit = repository(root)
    wrapper = trusted_git(root / "bin", cert)
    scratch = root / "scratch"
    scratch.mkdir()
    environment = {**os.environ, "PATH": str(wrapper), "TMPDIR": str(scratch)}
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

    def command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [str(cli), *arguments],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (arguments, result.stderr)
        assert not list(scratch.iterdir())
        return result

    def files(directory: Path) -> dict[str, bytes]:
        return {
            p.relative_to(directory).as_posix(): p.read_bytes()
            for p in directory.rglob("*")
            if p.is_file()
        }

    with https_server(cert, key, handler(root)) as url:
        remote = ["--git", url + "/repo.git", "--ref", commit, "--subdir", "service"]
        policies = ["--policy", "exposure.json", "--readiness-policy", "readiness.json"]
        for prefix, flags in [
            (["readiness"], ["--policy", "readiness.json", "--report"]),
            (["expose", "plan"], [*policies, "--plan"]),
        ]:
            actual = command([*prefix, *remote, *flags])
            expected = command([*prefix, str(source / "service"), *flags])
            assert actual.stdout == expected.stdout
            assert actual.stderr == f"Git snapshot: commit {commit}\n"
        for interface in ("rest", "mcp"):
            command(
                [
                    "expose",
                    "build",
                    interface,
                    *remote,
                    *policies,
                    "--output-dir",
                    "remote-" + interface,
                ]
            )
            command(
                [
                    "expose",
                    "build",
                    interface,
                    str(source / "service"),
                    *policies,
                    "--output-dir",
                    "local-" + interface,
                ]
            )
            assert files(root / ("remote-" + interface)) == files(
                root / ("local-" + interface)
            )
        docs = (
            Path(__file__).resolve().parents[1] / "docs/reference/git-sources.md"
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
# Deliberate execution of this trusted test fixture, after static acquisition
# and generation have completed. No optional transport server is started.
from apizr.repository_interfaces.runtime import load_bundle
for interface in ("rest", "mcp"):
    _, bindings, loader, _ = load_bundle(Path("python-" + interface), interface)
    try:
        assert bindings["python:calculator:add"](2, 3) == 5
    finally:
        loader.close()
""",
                url + "/repo.git",
                commit,
                "service",
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
            assert files(root / ("python-" + interface)) == files(
                root / ("local-" + interface)
            )
    print(
        "PASS Git HTTPS: minimal wheel, four CLI commands and documented Python API; exact parity after snapshot cleanup"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with TemporaryDirectory(prefix="apizr-git-wheel-") as directory:
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
