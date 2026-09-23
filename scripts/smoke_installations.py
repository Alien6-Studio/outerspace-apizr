"""Exercise the base wheel and every optional installation in separate environments."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with tempfile.TemporaryDirectory(prefix="apizr-installations-") as directory:
        root = Path(directory).resolve()
        source = root / "repository"
        source.mkdir()
        (source / "sample.py").write_text(
            "def add(a: int, b: int = 1) -> int: return a + b\n"
        )
        notebook = root / "sample.ipynb"
        notebook.write_text(
            json.dumps(
                {
                    "nbformat": 4,
                    "nbformat_minor": 5,
                    "metadata": {},
                    "cells": [
                        {
                            "cell_type": "code",
                            "id": "sample",
                            "metadata": {},
                            "execution_count": None,
                            "outputs": [],
                            "source": (source / "sample.py").read_text(),
                        }
                    ],
                }
            )
        )
        readiness = root / "readiness.json"
        readiness.write_text('{"execution":{"modes":["direct"],"require_controls":[]}}')
        exposure = root / "exposure.json"
        exposure.write_text(
            '{"selection":{"include":["python:sample:add"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}'
        )
        for extra in ("base", "notebook", "http", "mcp", "legacy"):
            env = root / ("env-" + extra)
            subprocess.run(
                ["uv", "venv", "--python", args.python, str(env)],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            python = env / "bin/python"
            cli = env / "bin/apizr"
            requirement = str(wheel) + ("" if extra == "base" else f"[{extra}]")
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--quiet",
                    "--python",
                    str(python),
                    requirement,
                ],
                check=True,
            )

            def command(*values, code=0, cli=cli, extra=extra):
                result = subprocess.run(
                    [str(cli), *map(str, values)],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert result.returncode == code, (
                    extra,
                    values,
                    result.stdout,
                    result.stderr,
                )
                return result

            def probe(code, python=python):
                subprocess.run(
                    [str(python), "-I", "-c", code], cwd=root, check=True, timeout=30
                )

            command("--help")
            command("inspect", source / "sample.py", "--ir")
            if extra == "base":
                probe(
                    "from importlib.metadata import distributions; names={d.metadata['Name'].lower().replace('_','-') for d in distributions()}; assert names == {'outerspace-apizr','pydantic','pydantic-core','annotated-types','typing-extensions','typing-inspection'}, names; print('Base installation: exactly 5 dependencies')"
                )
                for cmd, flag in (
                    ("scan", "--catalog"),
                    ("graph", "--graph"),
                    ("readiness", "--report"),
                ):
                    command(cmd, source, flag)
                command(
                    "expose",
                    "plan",
                    source,
                    "--readiness-policy",
                    readiness,
                    "--policy",
                    exposure,
                    "--plan",
                )
                for target in ("rest", "mcp"):
                    command(
                        "expose",
                        "build",
                        target,
                        source,
                        "--readiness-policy",
                        readiness,
                        "--policy",
                        exposure,
                        "--output-dir",
                        root / ("base-" + target),
                    )
                    command(
                        "generate",
                        target,
                        source / "sample.py",
                        "--output-dir",
                        root / ("single-" + target),
                    )
                # Execute the documented Python example with the base wheel,
                # outside the checkout. Block optional/CLI imports and plugin
                # discovery even if an environment accidentally provides them.
                documentation = (
                    Path(__file__).resolve().parents[1]
                    / "docs/reference/compiler-api.md"
                ).read_text(encoding="utf-8")
                example = documentation.split("```python\n", 1)[1].split("```", 1)[0]
                probe(
                    """import sys, importlib.metadata
def audit(event, args):
    if event == "import" and (
        args[0].split(".")[0] in {"fastapi", "mcp", "nbconvert", "IPython", "black", "questionary", "uvicorn", "docker"}
        or args[0] == "apizr.cli" or args[0].endswith("_cli")
        or args[0].startswith("apizr.extensions.plugins")
    ):
        raise AssertionError(args[0])
def forbidden(*args, **kwargs):
    raise AssertionError("plugin discovery")
sys.addaudithook(audit)
importlib.metadata.entry_points = forbidden
"""
                    + example
                    + """
from apizr.compiler import assess_readiness
from apizr.repository_readiness import report_bytes
from apizr.exposure import plan_bytes
assert report_bytes(assess_readiness(Path("repository"), readiness_policy=RepositoryReadinessPolicy.model_validate({"execution":{"modes":["direct"]}}))) == report_bytes(report)
assert rest["repository-readiness.json"] == report_bytes(report)
assert rest["exposure-plan.json"] == plan_bytes(plan)
for target in ("rest", "mcp"):
    def contents(directory):
        return {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert contents(Path("python-" + target)) == contents(Path("base-" + target))
print("PASS documented compiler API: base wheel, outside checkout, exact CLI parity")
"""
                )
                missing = command("inspect", notebook, code=2)
                assert (
                    "[notebook]" in missing.stderr and "Traceback" not in missing.stderr
                )
                missing = command("--script", source / "sample.py", code=2)
                assert (
                    "[legacy]" in missing.stderr and "Traceback" not in missing.stderr
                )
            elif extra == "notebook":
                command("inspect", notebook, "--ir")
                command(
                    "generate", "rest", notebook, "--output-dir", root / "notebook-rest"
                )
                probe(
                    "from importlib.util import find_spec; assert find_spec('fastapi') is None; assert find_spec('questionary') is None"
                )
            elif extra == "http":
                probe(
                    "import fastapi, uvicorn; from apizr.governed_repository.rest import create_app; from apizr.generators.rest.runtime import create_app; from importlib.util import find_spec; assert find_spec('nbconvert') is None"
                )
            elif extra == "mcp":
                probe(
                    "import mcp, uvicorn; from apizr.governed_repository.mcp import create_server; from importlib.util import find_spec; assert find_spec('nbconvert') is None"
                )
            else:
                result = json.loads(
                    command(
                        "--notebook", notebook, "--output-dir", root / "legacy"
                    ).stdout
                )
                assert {"Dockerfile", "requirements.txt", "sample_api.py"} <= set(
                    result["files"]
                )
                probe(
                    "from apizr.app import app; assert app.title == 'OuterSpace Apizr'"
                )
            print(f"PASS isolated installation: {extra}")


if __name__ == "__main__":
    main()
