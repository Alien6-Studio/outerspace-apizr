"""Validate a built wheel and exercise its installed CLI outside the checkout."""

import argparse
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert "apizr/__init__.py" in names
        assert "apizr/capabilities/model.py" in names
        assert "apizr/readiness/model.py" in names
        assert not any(name == "src.py" or name.startswith("src/") for name in names)
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in names)
        assert "apizr/modules/fast_apizr/generator/templates/fastApiApp.j2" in names
        assert "apizr/i18n/en/messages.json" in names
    notebook = Path(__file__).resolve().parents[1] / "examples/pricing.ipynb"
    with tempfile.TemporaryDirectory(prefix="apizr-wheel-") as directory:
        root = Path(directory)
        env = root / "env"
        subprocess.run(["uv", "venv", "--python", args.python, str(env)], check=True)
        bin_dir = env / ("Scripts" if sys.platform == "win32" else "bin")
        python = bin_dir / "python"
        cli = bin_dir / "apizr"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel)], check=True
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                """import apizr, importlib.util
from apizr.capabilities import inspect_source, canonical_bytes, document_digest
assert apizr.__file__
assert importlib.util.find_spec('src') is None
ir = inspect_source(b'def work(x: int) -> int: return x', module_name='installed')
assert ir.schema_version == 'apizr.capability/v1'
assert ir.capabilities[0].id == 'python:installed:work'
assert canonical_bytes(ir).endswith(b'\\n')
assert len(document_digest(ir).value) == 64
print(apizr.__file__)
""",
            ],
            cwd=root,
            check=True,
        )
        subprocess.run(
            [str(cli), "--help"], cwd=root, check=True, stdout=subprocess.DEVNULL
        )
        # Both inputs live outside the repository; the installed CLI must be sufficient.
        source = root / "sample.py"
        source.write_text("def total(values: list[int]) -> int: return sum(values)\n")
        local_notebook = root / "sample.ipynb"
        local_notebook.write_text(
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
                            "source": source.read_text(),
                        }
                    ],
                }
            )
        )
        for target in (source, local_notebook):
            command = [
                str(cli),
                "inspect",
                str(target),
                "--module-name",
                "installed.sample",
            ]
            inspected = subprocess.run(
                command + ["--format", "json"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            report = json.loads(inspected.stdout)
            assert report["schema_version"] == "apizr.inspection/v1"
            assert report["readiness"]["policy_version"] == "apizr.readiness/v1"
            assessment = report["readiness"]["assessments"][0]
            assert (
                assessment["state"] == "ready" and assessment["can_generate_interface"]
            )
            canonical = subprocess.run(
                command + ["--ir"], cwd=root, check=True, capture_output=True
            )
            assert json.loads(canonical.stdout) == report["capability_ir"]
            text = subprocess.run(
                command, cwd=root, check=True, capture_output=True, text=True
            )
            assert "readiness: READY" in text.stdout
        result = subprocess.run(
            [
                str(cli),
                "--notebook",
                str(notebook),
                "--output-dir",
                str(root / "project"),
                "--force",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        manifest = json.loads(result.stdout)
        assert manifest["api_module"] == "pricing_api"
        assert {
            "pricing.py",
            "pricing.json",
            "pricing_api.py",
            "requirements.txt",
            "Dockerfile",
            "start.sh",
        } <= set(manifest["files"])
        for name in manifest["files"]:
            assert (root / "project" / name).is_file()
        print(
            "Wheel namespace, Capability IR, readiness inspection (Python/notebook), resources, license, CLI help and notebook generation passed."
        )


if __name__ == "__main__":
    main()
